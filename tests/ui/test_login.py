"""Passkey login end to end, with Chrome's virtual authenticator (no Touch ID needed).

Starts its own Parla on http://localhost:7872 with PARLA_ORIGIN set; passkeys need a
host name (not 127.0.0.1) and a secure context (https, or http on localhost).
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui

ORIGIN = "http://localhost:7872"
ROOT = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def login_server(tmp_path_factory):
    dead = "http://127.0.0.1:9"
    env = {
        **os.environ,
        "GRADIO_SERVER_NAME": "127.0.0.1",
        "GRADIO_SERVER_PORT": "7872",
        "PARLA_ORIGIN": ORIGIN,
        "PARLA_DATA_DIR": str(tmp_path_factory.mktemp("data")),
        "PARLA_OPEN_BROWSER": "0",
        "OLLAMA_HOST": dead,
        "PARLA_SPEECH_HOST": dead,
        "PYTHONUNBUFFERED": "1",
    }
    proc = subprocess.Popen(
        ["uv", "run", "--quiet", "python", "-m", "parla.app"],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    found: dict[str, str] = {}

    def read():
        for line in proc.stdout:
            if m := re.search(r"(\S+/login#setup=\S+)", line):
                found["link"] = m.group(1)

    threading.Thread(target=read, daemon=True).start()
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(f"{ORIGIN}/login", timeout=1)
                if "link" in found:
                    break
            except OSError:
                pass
            if proc.poll() is not None:
                pytest.fail("Parla exited during startup")
            time.sleep(0.5)
        else:
            pytest.fail("Parla with login did not start or printed no setup link")
        yield found["link"]
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_passkey_login(browser, login_server):
    context = browser.new_context()
    page = context.new_page()
    cdp = context.new_cdp_session(page)
    cdp.send("WebAuthn.enable")
    cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {
        "protocol": "ctap2", "transport": "internal", "hasResidentKey": True,
        "hasUserVerification": True, "isUserVerified": True, "automaticPresenceSimulation": True,
    }})

    # Logged out: the app sends you to the login page.
    page.goto(ORIGIN)
    page.wait_for_url(f"{ORIGIN}/login")

    # First passkey via the setup link from the server log.
    page.goto(login_server)
    page.fill("#setupName", "Testgerät")
    page.click("#setupButton")
    page.wait_for_url(f"{ORIGIN}/")
    page.wait_for_selector("#parla-nav-trainer")

    # The setup link is used up.
    token = login_server.split("#setup=")[1]
    assert page.request.post(f"{ORIGIN}/auth/setup/options", data={"token": token}).status == 403

    # Sign out, then back in with the passkey.
    page.goto(f"{ORIGIN}/passkeys")
    page.wait_for_selector("text=Testgerät")
    page.click("#logout")
    page.wait_for_url(f"{ORIGIN}/login")
    assert page.request.get(f"{ORIGIN}/auth/passkeys").status == 401
    page.click("#passkeyButton")
    page.wait_for_url(f"{ORIGIN}/")
    page.wait_for_selector("#parla-nav-trainer")
    assert page.request.get(f"{ORIGIN}/auth/passkeys").json()[0]["lastUsedAt"]
    context.close()
