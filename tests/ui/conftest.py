"""Browser tests: drive Parla with Playwright in the installed Google Chrome.

The app runs in the test setup from scripts/test-server.sh (see README "Tests"):
http://127.0.0.1:7871, fresh data directory, "Mac Mini off". If that server is
already running (you started the script yourself), the tests use it; otherwise they
start it and stop it afterwards. PARLA_UI_HEADED=1 shows the browser while testing.
"""

from __future__ import annotations

import os
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

URL = "http://127.0.0.1:7871"
SCRIPT = Path(__file__).parents[2] / "scripts" / "test-server.sh"


def running() -> bool:
    try:
        urllib.request.urlopen(URL, timeout=1)
        return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def app_url(tmp_path_factory):
    if running():
        yield URL
        return
    env = {**os.environ, "PARLA_OPEN_BROWSER": "0", "PARLA_TEST_DATA": str(tmp_path_factory.mktemp("data"))}
    proc = subprocess.Popen([SCRIPT], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        for _ in range(120):
            if running():
                break
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
        headed = os.environ.get("PARLA_UI_HEADED") == "1"
        b = p.chromium.launch(channel="chrome", headless=not headed, slow_mo=500 if headed else 0)
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
