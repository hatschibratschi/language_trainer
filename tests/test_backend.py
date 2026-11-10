import socket
import time

import httpx
import pytest

from parla import backend, config


@pytest.fixture(autouse=True)
def fresh_status():
    backend.forget()
    yield
    backend.forget()


def closed_port() -> str:
    """A local address where nothing listens (connections are refused at once)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{s.getsockname()[1]}"


def test_offline_mac_is_detected_quickly(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_HOST", closed_port())
    monkeypatch.setattr(config, "SPEECH_HOST", closed_port())
    start = time.monotonic()
    s = backend.status()
    assert time.monotonic() - start < backend.PROBE_TIMEOUT + 1
    assert s == backend.Status(ollama=False, speech=False, models=[])
    assert not s.online


def test_status_is_cached_until_forgotten(monkeypatch):
    calls = []
    monkeypatch.setattr(backend, "_probe_ollama", lambda: calls.append(1) or ["gemma3:27b"])
    monkeypatch.setattr(backend, "_probe_speech", lambda: True)
    assert backend.status().online
    backend.status()
    assert len(calls) == 1
    backend.status(force=True)
    assert len(calls) == 2
    backend.forget()
    backend.status()
    assert len(calls) == 3


def test_online_needs_a_chat_model():
    assert not backend.Status(ollama=True, models=[]).online
    assert backend.Status(ollama=True, models=["qwen3:14b"]).online
    assert backend.chat_models(["nomic-embed-text", "bge-m3", "qwen3:14b"]) == ["qwen3:14b"]


def test_connection_errors_become_the_offline_message(monkeypatch):
    monkeypatch.setattr(backend, "_probe_ollama", lambda: ["gemma3:27b"])
    monkeypatch.setattr(backend, "_probe_speech", lambda: True)
    backend.status()
    assert backend.error_message(httpx.ConnectTimeout("timed out")) == backend.OFFLINE_MESSAGE
    assert backend._cached is None  # the next check asks the Mac again
    assert "kaputt" in backend.error_message(RuntimeError("kaputt"))
