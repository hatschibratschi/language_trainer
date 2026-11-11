"""Login with passkeys (WebAuthn) only, for the whole app.

Active when PARLA_ORIGIN is set (e.g. https://parla.178-104-161-250.sslip.io); the passkeys are
tied to its host name. A successful login sets a signed session cookie for 30 days; no sessions
are kept on the server. While no passkey is registered, the server logs a one-time setup link
that registers the first one. Further passkeys are added and removed on /passkeys.

Same design as the vacanze blog editor (server/auth.js there), ported to Python.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

COOKIE = "parla_session"
SESSION_DAYS = 30
CHALLENGE_SECONDS = 5 * 60
PAGES = Path(__file__).parent / "auth_pages"
# Reachable without login, so the login page works.
PUBLIC_PATHS = {
    "/login",
    "/auth/login.js",
    "/auth/status",
    "/auth/setup/options",
    "/auth/setup/verify",
    "/auth/passkey/options",
    "/auth/passkey/verify",
    "/auth/logout",
}


class AuthError(Exception):
    """A failed check, shown to the user as the error message."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class Auth:
    def __init__(self, data_dir: str | Path, origin: str):
        self.origin = origin.rstrip("/")
        self.rp_id = urlsplit(self.origin).hostname or ""
        self.secure_cookie = self.origin.startswith("https:")
        self.dir = Path(data_dir) / "auth"
        self.passkey_file = self.dir / "passkeys.json"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.secret = self._load_secret()
        self.challenges: dict[str, tuple[str, float]] = {}  # challenge -> (type, expires)
        self.setup_token: str | None = None
        self.lock = threading.Lock()
        self.ensure_setup_token(self.read_passkeys())

    # ---------- Storage ----------

    def _load_secret(self) -> bytes:
        path = self.dir / "session-secret"
        try:
            return path.read_bytes()
        except FileNotFoundError:
            secret = secrets.token_urlsafe(32).encode()
            path.write_bytes(secret)
            path.chmod(0o600)
            return secret

    def read_passkeys(self) -> list[dict]:
        """[{id, publicKey, counter, transports, name, createdAt, lastUsedAt}]"""
        try:
            return json.loads(self.passkey_file.read_text())
        except FileNotFoundError:
            return []

    def write_passkeys(self, passkeys: list[dict]) -> None:
        tmp = self.passkey_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(passkeys, indent=2))
        tmp.chmod(0o600)
        tmp.replace(self.passkey_file)

    # ---------- Setup link (only while there is no passkey) ----------

    def ensure_setup_token(self, passkeys: list[dict]) -> None:
        if passkeys:
            self.setup_token = None
        elif not self.setup_token:
            self.setup_token = secrets.token_urlsafe(24)
            print(
                "No passkey registered yet. Open this link to create the first one:\n"
                f"  {self.origin}/login#setup={self.setup_token}",
                flush=True,
            )

    def check_setup_token(self, token) -> None:
        if not (self.setup_token and isinstance(token, str) and hmac.compare_digest(token, self.setup_token)):
            raise AuthError("Dieser Einrichtungslink ist nicht (mehr) gültig.", 403)

    # ---------- Challenges (one use each, short-lived) ----------

    def remember_challenge(self, challenge: bytes, kind: str) -> None:
        now = time.time()
        for c, (_, expires) in list(self.challenges.items()):
            if expires < now:
                del self.challenges[c]
        self.challenges[bytes_to_base64url(challenge)] = (kind, now + CHALLENGE_SECONDS)

    def take_challenge(self, credential: dict, kind: str) -> bytes:
        """The challenge the browser signed, if we issued it for `kind` and it is still valid."""
        try:
            client_data = json.loads(base64url_to_bytes(credential["response"]["clientDataJSON"]))
            challenge = client_data["challenge"]
        except Exception:
            raise AuthError("Ungültige Antwort vom Browser.") from None
        entry = self.challenges.pop(challenge, None)
        if not entry or entry[0] != kind or entry[1] < time.time():
            raise AuthError("Die Anfrage ist abgelaufen. Bitte noch einmal versuchen.")
        return base64url_to_bytes(challenge)

    # ---------- Registering passkeys ----------

    def registration_options(self, kind: str) -> dict:
        options = generate_registration_options(
            rp_id=self.rp_id,
            rp_name="Parla",
            user_name="parla",
            user_display_name="Parla",
            # Same account on every device, so a phone keeps one passkey for this site.
            user_id=hashlib.sha256(b"parla-login").digest()[:16],
            exclude_credentials=[
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(p["id"])) for p in self.read_passkeys()
            ],
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )
        self.remember_challenge(options.challenge, kind)
        return json.loads(options_to_json(options))

    def register(self, credential, name, kind: str) -> None:
        if not isinstance(credential, dict):
            raise AuthError("Ungültige Antwort vom Browser.")
        challenge = self.take_challenge(credential, kind)
        try:
            result = verify_registration_response(
                credential=credential,
                expected_challenge=challenge,
                expected_origin=self.origin,
                expected_rp_id=self.rp_id,
                require_user_verification=True,
            )
        except Exception as e:
            raise AuthError(f"Passkey-Prüfung fehlgeschlagen: {e}") from None
        with self.lock:
            passkeys = self.read_passkeys()
            cred_id = bytes_to_base64url(result.credential_id)
            if any(p["id"] == cred_id for p in passkeys):
                raise AuthError("Dieser Passkey ist schon registriert.")
            name = str(name or "").strip()[:60] or f"Passkey {len(passkeys) + 1}"
            passkeys.append({
                "id": cred_id,
                "publicKey": bytes_to_base64url(result.credential_public_key),
                "counter": result.sign_count,
                "transports": credential.get("response", {}).get("transports") or [],
                "name": name,
                "createdAt": _now(),
                "lastUsedAt": None,
            })
            self.write_passkeys(passkeys)
            self.ensure_setup_token(passkeys)

    # ---------- Login ----------

    def authentication_options(self) -> dict:
        # "required": the browser always asks for Touch ID / Face ID / PIN; checked again below.
        options = generate_authentication_options(
            rp_id=self.rp_id, user_verification=UserVerificationRequirement.REQUIRED
        )
        self.remember_challenge(options.challenge, "login")
        return json.loads(options_to_json(options))

    def authenticate(self, credential) -> None:
        if not isinstance(credential, dict):
            raise AuthError("Ungültige Antwort vom Browser.")
        with self.lock:
            passkeys = self.read_passkeys()
            passkey = next((p for p in passkeys if p["id"] == credential.get("id")), None)
            if not passkey:
                raise AuthError("Dieser Passkey ist hier nicht (mehr) registriert.", 401)
            challenge = self.take_challenge(credential, "login")
            try:
                result = verify_authentication_response(
                    credential=credential,
                    expected_challenge=challenge,
                    expected_origin=self.origin,
                    expected_rp_id=self.rp_id,
                    credential_public_key=base64url_to_bytes(passkey["publicKey"]),
                    credential_current_sign_count=passkey["counter"],
                    require_user_verification=True,
                )
            except Exception as e:
                raise AuthError(f"Passkey-Prüfung fehlgeschlagen: {e}", 401) from None
            passkey["counter"] = result.new_sign_count
            passkey["lastUsedAt"] = _now()
            self.write_passkeys(passkeys)

    def remove(self, cred_id: str) -> None:
        with self.lock:
            passkeys = self.read_passkeys()
            rest = [p for p in passkeys if p["id"] != cred_id]
            if len(rest) == len(passkeys):
                raise AuthError("Passkey nicht gefunden.", 404)
            if not rest:
                raise AuthError("Das ist dein letzter Passkey. Füge zuerst einen weiteren hinzu.", 409)
            self.write_passkeys(rest)

    # ---------- Session cookie: "<expires>.<hmac>" ----------

    def _sign(self, value: str) -> str:
        return bytes_to_base64url(hmac.new(self.secret, value.encode(), hashlib.sha256).digest())

    def session_value(self, days: float = SESSION_DAYS) -> str:
        expires = str(int(time.time() + days * 86400))
        return f"{expires}.{self._sign(expires)}"

    def valid_session(self, value: str | None) -> bool:
        expires, _, sig = (value or "").partition(".")
        if not expires.isdigit() or int(expires) < time.time():
            return False
        return hmac.compare_digest(sig, self._sign(expires))

    def set_session(self, response) -> None:
        response.set_cookie(
            COOKIE,
            self.session_value(),
            max_age=SESSION_DAYS * 86400,
            path="/",
            httponly=True,
            secure=self.secure_cookie,
            # Lax, not Strict: opening the app from a link or the home screen keeps the session.
            samesite="lax",
        )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _cookie(headers: list[tuple[bytes, bytes]]) -> str | None:
    for key, value in headers:
        if key == b"cookie":
            for part in value.decode("latin-1").split(";"):
                name, _, val = part.strip().partition("=")
                if name == COOKIE:
                    return val
    return None


class LoginRequired:
    """ASGI middleware: everything except the login routes needs a valid session cookie."""

    def __init__(self, app: ASGIApp, auth: Auth):
        self.app = app
        self.auth = auth

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] not in ("http", "websocket")
            or scope["path"] in PUBLIC_PATHS
            or self.auth.valid_session(_cookie(scope["headers"]))
        ):
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 4401})
        accept = dict(scope["headers"]).get(b"accept", b"").decode()
        if scope["method"] == "GET" and "text/html" in accept:
            response = RedirectResponse("/login", status_code=303)
        else:
            response = JSONResponse(
                {"error": "Du bist abgemeldet. Lade die Seite neu, um dich anzumelden."}, status_code=401
            )
        await response(scope, receive, send)


def router(auth: Auth) -> APIRouter:
    r = APIRouter()
    no_store = {"Cache-Control": "no-store"}

    def page(name: str) -> FileResponse:
        return FileResponse(PAGES / name, headers={"Cache-Control": "no-cache"})

    async def body(request: Request) -> dict:
        try:
            data = await request.json()
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def ok() -> JSONResponse:
        return JSONResponse({"ok": True})

    def handle(fn):
        async def wrapper(request: Request):
            try:
                return await fn(request)
            except AuthError as e:
                return JSONResponse({"error": str(e)}, status_code=e.status)

        return wrapper

    # ----- Login (public) -----

    r.get("/login", include_in_schema=False)(lambda: page("login.html"))
    r.get("/auth/login.js", include_in_schema=False)(lambda: page("login.js"))
    r.get("/passkeys", include_in_schema=False)(lambda: page("passkeys.html"))

    @r.get("/auth/status")
    async def status(request: Request):
        passkeys = auth.read_passkeys()
        auth.ensure_setup_token(passkeys)  # picks up a deleted passkeys.json without a restart
        return JSONResponse(
            {"loggedIn": auth.valid_session(request.cookies.get(COOKIE)), "passkeys": bool(passkeys)},
            headers=no_store,
        )

    @r.post("/auth/setup/options")
    @handle
    async def setup_options(request: Request):
        auth.check_setup_token((await body(request)).get("token"))
        return JSONResponse(auth.registration_options("setup"))

    @r.post("/auth/setup/verify")
    @handle
    async def setup_verify(request: Request):
        data = await body(request)
        auth.check_setup_token(data.get("token"))
        auth.register(data.get("response"), data.get("name"), "setup")
        response = ok()
        auth.set_session(response)
        return response

    @r.post("/auth/passkey/options")
    async def login_options():
        return JSONResponse(auth.authentication_options())

    @r.post("/auth/passkey/verify")
    @handle
    async def login_verify(request: Request):
        auth.authenticate((await body(request)).get("response"))
        response = ok()
        auth.set_session(response)
        return response

    @r.post("/auth/logout")
    async def logout():
        response = ok()
        response.delete_cookie(COOKIE, path="/")
        return response

    # ----- Managing passkeys (login needed, see LoginRequired) -----

    @r.get("/auth/passkeys")
    async def list_passkeys():
        keys = [
            {k: p[k] for k in ("id", "name", "createdAt", "lastUsedAt")} for p in auth.read_passkeys()
        ]
        return JSONResponse(keys, headers=no_store)

    @r.post("/auth/passkeys/options")
    async def add_options():
        return JSONResponse(auth.registration_options("register"))

    @r.post("/auth/passkeys/verify")
    @handle
    async def add_verify(request: Request):
        data = await body(request)
        auth.register(data.get("response"), data.get("name"), "register")
        return ok()

    @r.post("/auth/passkeys/remove")
    @handle
    async def remove(request: Request):
        auth.remove(str((await body(request)).get("id", "")))
        return ok()

    return r


def from_env(data_dir: str | Path) -> Auth | None:
    origin = os.environ.get("PARLA_ORIGIN", "").strip()
    return Auth(data_dir, origin) if origin else None
