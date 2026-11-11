"""Passkey login: session cookie, setup link, and which routes need a login.

The WebAuthn ceremony itself is tested in the browser (tests/ui/test_login.py).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from parla.auth import COOKIE, Auth, AuthError, LoginRequired, router


@pytest.fixture
def auth(tmp_path):
    return Auth(tmp_path, "https://parla.example.org")


@pytest.fixture
def client(auth):
    app = FastAPI()
    app.include_router(router(auth))
    app.add_middleware(LoginRequired, auth=auth)

    @app.get("/")
    def home():
        return {"app": True}

    @app.post("/gradio_api/queue/join")
    def join():
        return {"joined": True}

    return TestClient(app, base_url="https://parla.example.org", follow_redirects=False)


def test_rp_id_is_host_name(auth):
    assert auth.rp_id == "parla.example.org"


def test_session_cookie(auth):
    assert auth.valid_session(auth.session_value())
    assert not auth.valid_session(auth.session_value(days=-1))
    expires, _, sig = auth.session_value().partition(".")
    assert not auth.valid_session(f"{int(expires) + 999}.{sig}")
    assert not auth.valid_session("garbage")
    assert not auth.valid_session(None)


def test_session_secret_survives_restart(tmp_path):
    value = Auth(tmp_path, "https://a.org").session_value()
    assert Auth(tmp_path, "https://a.org").valid_session(value)


def test_setup_link_only_without_passkeys(capsys, tmp_path):
    auth = Auth(tmp_path, "https://parla.example.org")
    assert auth.setup_token
    assert f"https://parla.example.org/login#setup={auth.setup_token}" in capsys.readouterr().out
    auth.check_setup_token(auth.setup_token)
    with pytest.raises(AuthError):
        auth.check_setup_token("wrong")
    auth.write_passkeys([{"id": "x"}])
    auth.ensure_setup_token(auth.read_passkeys())
    assert auth.setup_token is None
    with pytest.raises(AuthError):
        auth.check_setup_token(None)


def test_challenge_is_single_use_and_typed(auth):
    import json

    from webauthn.helpers import bytes_to_base64url

    auth.remember_challenge(b"abc", "login")
    client_data = bytes_to_base64url(json.dumps({"challenge": bytes_to_base64url(b"abc")}).encode())
    cred = {"response": {"clientDataJSON": client_data}}
    with pytest.raises(AuthError):
        auth.take_challenge(cred, "setup")  # wrong type uses it up
    auth.remember_challenge(b"abc", "login")
    assert auth.take_challenge(cred, "login") == b"abc"
    with pytest.raises(AuthError):
        auth.take_challenge(cred, "login")


def test_cannot_remove_last_passkey(auth):
    auth.write_passkeys([{"id": "a"}, {"id": "b"}])
    auth.remove("a")
    with pytest.raises(AuthError, match="letzter"):
        auth.remove("b")
    with pytest.raises(AuthError):
        auth.remove("nope")


def test_logged_out(client):
    page = client.get("/", headers={"Accept": "text/html"})
    assert page.status_code == 303 and page.headers["location"] == "/login"
    assert client.post("/gradio_api/queue/join").status_code == 401
    assert client.get("/auth/passkeys").status_code == 401
    assert client.get("/login").status_code == 200
    assert client.get("/auth/login.js").status_code == 200
    assert client.get("/auth/status").json() == {"loggedIn": False, "passkeys": False}
    assert client.post("/auth/passkey/options").json()["rpId"] == "parla.example.org"
    assert client.post("/auth/setup/options", json={"token": "wrong"}).status_code == 403


def test_logged_in(client, auth):
    client.cookies.set(COOKIE, auth.session_value())
    assert client.get("/").json() == {"app": True}
    assert client.post("/gradio_api/queue/join").json() == {"joined": True}
    assert client.get("/auth/status").json()["loggedIn"] is True
    assert client.get("/auth/passkeys").json() == []
    options = client.post("/auth/passkeys/options").json()
    assert options["rp"]["id"] == "parla.example.org"
    assert options["authenticatorSelection"]["userVerification"] == "required"
    logout = client.post("/auth/logout")
    assert COOKIE in logout.headers["set-cookie"] and "Max-Age=0" in logout.headers["set-cookie"]


def test_session_cookie_flags(auth):
    from starlette.responses import Response

    r = Response()
    auth.set_session(r)
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "samesite=lax" in cookie.lower()
