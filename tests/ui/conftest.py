"""Browser tests: start Parla in a subprocess and drive it with Playwright.

Always the same setup (see README "UI tests"): port 7871, a fresh temporary data
directory, and Ollama / parla-speech pointed at an unused port, so the app runs as
if the Mac Mini were off. The browser is the installed Google Chrome.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request

import pytest

PORT = 7871
URL = f"http://127.0.0.1:{PORT}"
DEAD = "http://127.0.0.1:9"  # nothing listens there: "Mac Mini off"


@pytest.fixture(scope="session")
def app_url(tmp_path_factory):
    env = {
        **os.environ,
        "GRADIO_SERVER_NAME": "127.0.0.1",
        "GRADIO_SERVER_PORT": str(PORT),
        "PARLA_OPEN_BROWSER": "0",
        "PARLA_DATA_DIR": str(tmp_path_factory.mktemp("data")),
        "OLLAMA_HOST": DEAD,
        "PARLA_SPEECH_HOST": DEAD,
    }
    for key in ("PARLA_AUTH_USER", "PARLA_AUTH_PASSWORD"):
        env.pop(key, None)
    proc = subprocess.Popen([sys.executable, "-m", "parla.app"], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(URL, timeout=1)
                break
            except OSError:
                if proc.poll() is not None:
                    pytest.fail("Parla exited during startup")
                time.sleep(0.5)
        else:
            pytest.fail(f"Parla did not start on {URL}")
        yield URL
    finally:
        proc.terminate()
        proc.wait(10)


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        yield b
        b.close()


@pytest.fixture(params=[(390, 844), (1280, 800)], ids=["phone", "desktop"])
def page(request, browser, app_url):
    w, h = request.param
    pg = browser.new_page(viewport={"width": w, "height": h})
    pg.goto(app_url)
    # Last step of the page-load chain: with the Mac Mini off the app switches to the
    # trainer. Before that, clicks can be undone by the load updates.
    pg.wait_for_function("document.querySelector('#parla-nav-trainer')?.classList.contains('primary')")
    yield pg
    pg.close()
