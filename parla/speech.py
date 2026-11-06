"""Client for the parla-speech service (speech-to-text and text-to-speech)."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

import numpy as np

from parla.config import SPEECH_HOST

SLOW_SPEED = 0.75  # "langsam": 75 % of the normal speaking rate


class SpeechError(RuntimeError):
    pass


def _request(path: str, body: bytes, content_type: str, timeout: float) -> bytes:
    req = urllib.request.Request(
        SPEECH_HOST.rstrip("/") + path, data=body, headers={"Content-Type": content_type}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as err:
        try:
            detail = json.loads(err.read()).get("error", "")
        except Exception:  # noqa: BLE001
            detail = ""
        raise SpeechError(f"Sprachdienst: {detail or err}") from err
    except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
        raise SpeechError(
            f"Sprachdienst nicht erreichbar ({SPEECH_HOST}). Läuft parla-speech auf dem Mac?"
        ) from err


def transcribe(
    audio_path: str | Path, language: str, prompt: str | None = None, timeout: float = 120
) -> str:
    """prompt: text the speech is likely related to (e.g. the tutor's last reply). Whisper
    then expects its words, which helps a lot with a beginner's unclear pronunciation."""
    data = Path(audio_path).read_bytes()
    query = {"language": language, **({"prompt": prompt} if prompt else {})}
    raw = _request(f"/stt?{urllib.parse.urlencode(query)}", data, "application/octet-stream", timeout)
    return str(json.loads(raw)["text"]).strip()


def synthesize(text: str, voice: str, speed: float = 1.0, timeout: float = 60) -> bytes:
    body = json.dumps({"text": text, "voice": voice, "speed": speed}).encode()
    return _request("/tts", body, "application/json", timeout)


def wav_to_numpy(data: bytes) -> tuple[int, np.ndarray]:
    """WAV bytes -> (sample_rate, int16 array), the format gr.Audio accepts as a value."""
    with wave.open(io.BytesIO(data)) as w:
        rate, channels = w.getframerate(), w.getnchannels()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    return rate, pcm.reshape(-1, channels) if channels > 1 else pcm
