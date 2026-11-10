"""The Mac Mini's services as seen from the web app: Ollama (LLM) and parla-speech.

The web app may run on an always-on server while the Mac is switched off most of the
time. Everything that needs the Mac (chat, lookup, voice) checks here first, with short
timeouts, so the rest of the app (vocabulary trainer, list editor) never waits for it.
"""

from __future__ import annotations

import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import httpx
import ollama

from parla import config

# An offline Tailscale peer doesn't refuse connections, it just never answers,
# so every request to the Mac needs a short connect timeout.
CONNECT_TIMEOUT = 3.0
PROBE_TIMEOUT = 2.0  # health checks
CHAT_TIMEOUT = 600.0  # a long answer from a big model, including loading it
STATUS_TTL = 10.0  # seconds a health check result is reused

OFFLINE_MESSAGE = (
    "Der Mac Mini ist nicht erreichbar. Gespräch, Nachschlagen und Sprache brauchen ihn – "
    "bitte einschalten. Vokabeltrainer und Listen funktionieren auch ohne."
)


def ollama_client(timeout: float = CHAT_TIMEOUT) -> ollama.Client:
    return ollama.Client(
        host=config.OLLAMA_HOST,
        timeout=httpx.Timeout(timeout, connect=min(CONNECT_TIMEOUT, timeout)),
    )


@dataclass(frozen=True)
class Status:
    ollama: bool = False
    speech: bool = False
    models: list[str] = field(default_factory=list)

    @property
    def online(self) -> bool:
        """The chat works (Ollama answers and has at least one chat model)."""
        return self.ollama and bool(self.models)


def chat_models(names: list[str]) -> list[str]:
    # Embedding models can't chat.
    return sorted(n for n in names if "embed" not in n and "bge" not in n)


def _probe_ollama() -> list[str] | None:
    try:
        listing = ollama_client(PROBE_TIMEOUT).list()
        return chat_models([m["model"] for m in listing["models"]])  # type: ignore[index]
    except Exception:  # noqa: BLE001 – any failure means "not usable right now"
        return None


def _probe_speech() -> bool:
    try:
        url = config.SPEECH_HOST.rstrip("/") + "/health"
        with urllib.request.urlopen(url, timeout=PROBE_TIMEOUT) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


_lock = threading.Lock()
_cached: tuple[float, Status] | None = None


def status(force: bool = False) -> Status:
    """Is the Mac there? Probes Ollama and parla-speech in parallel (at most
    ~PROBE_TIMEOUT seconds) and reuses the answer for STATUS_TTL seconds."""
    global _cached
    with _lock:
        if not force and _cached and time.monotonic() - _cached[0] < STATUS_TTL:
            return _cached[1]
        with ThreadPoolExecutor(2) as pool:
            models_f, speech_f = pool.submit(_probe_ollama), pool.submit(_probe_speech)
            models, speech_ok = models_f.result(), speech_f.result()
        result = Status(ollama=models is not None, speech=speech_ok, models=models or [])
        _cached = (time.monotonic(), result)
        return result


def forget() -> None:
    """Drop the cached status, e.g. after a request to the Mac failed."""
    global _cached
    with _lock:
        _cached = None


def is_connection_error(err: BaseException) -> bool:
    return isinstance(err, (httpx.TransportError, ConnectionError, TimeoutError))


def error_message(err: BaseException) -> str:
    """A user-facing message for a failed call to Ollama."""
    if is_connection_error(err):
        forget()
        return OFFLINE_MESSAGE
    return f"Fehler beim Aufruf von Ollama: {err}"
