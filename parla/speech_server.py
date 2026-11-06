"""parla-speech: a small local HTTP service for speech-to-text and text-to-speech.

Runs natively on the Mac (like Ollama), because only there Whisper gets the Apple GPU
via MLX. The Parla container reaches it at host.docker.internal:11500.

    POST /stt?language=it   body: audio file (WAV; other formats via macOS afconvert)
                            -> {"text": "..."}
    POST /tts               body: {"text": "...", "voice": "it_IT-paola-medium", "speed": 1.0}
                            -> audio/wav
    GET  /health            -> {"ok": true, ...}

Only standard-library HTTP, so the Parla app needs no extra packages to talk to it.
"""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qs, urlparse

import numpy as np

from parla.config import SPEECH_PORT, STT_MODEL

log = logging.getLogger("parla-speech")

WHISPER_RATE = 16_000
MAX_UPLOAD = 50 * 1024 * 1024  # ~ several minutes of WAV; push-to-talk turns are short
MAX_TTS_CHARS = 2_000
VOICES_DIR = Path(
    os.environ.get("PARLA_VOICES_DIR", Path.home() / ".local" / "share" / "parla" / "voices")
)


# --- audio helpers -----------------------------------------------------------


def wav_to_float(data: bytes) -> tuple[int, np.ndarray]:
    """Decode 16-bit PCM WAV into (sample_rate, mono float32 in [-1, 1])."""
    with wave.open(io.BytesIO(data)) as w:
        if w.getsampwidth() != 2:
            raise ValueError("only 16-bit WAV is supported")
        rate, channels = w.getframerate(), w.getnchannels()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    audio = pcm.astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return rate, audio


def resample(audio: np.ndarray, rate: int, target: int = WHISPER_RATE) -> np.ndarray:
    """Linear resampling; plenty for speech recognition."""
    if rate == target or len(audio) == 0:
        return audio.astype(np.float32)
    n = int(round(len(audio) * target / rate))
    x = np.linspace(0, len(audio) - 1, n)
    return np.interp(x, np.arange(len(audio)), audio).astype(np.float32)


def convert_with_afconvert(data: bytes) -> bytes:
    """Turn any format macOS understands (m4a/AAC from iPhone, mp3, caf, …) into WAV."""
    if not shutil.which("afconvert"):
        raise ValueError("unsupported audio format (only WAV without macOS afconvert)")
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in", Path(tmp) / "out.wav"
        src.write_bytes(data)
        result = subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", f"LEI16@{WHISPER_RATE}", "-c", "1", str(src), str(dst)],
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise ValueError("could not decode audio: " + result.stderr.decode(errors="replace"))
        return dst.read_bytes()


def decode_audio(data: bytes) -> np.ndarray:
    """Any uploaded audio -> mono float32 at 16 kHz, as Whisper expects."""
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        try:
            rate, audio = wav_to_float(data)
            return resample(audio, rate)
        except (ValueError, wave.Error):
            pass  # e.g. 32-bit float WAV: let afconvert handle it
    rate, audio = wav_to_float(convert_with_afconvert(data))
    return resample(audio, rate)


def float_to_wav(audio: np.ndarray, rate: int) -> bytes:
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


# --- engines -----------------------------------------------------------------


class Engine(Protocol):
    def transcribe(self, audio: np.ndarray, language: str) -> str: ...
    def synthesize(self, text: str, voice: str, speed: float) -> bytes: ...


class LocalEngine:
    """mlx-whisper for STT, Piper for TTS. Models load lazily and stay in memory."""

    def __init__(self, stt_model: str = STT_MODEL, voices_dir: Path = VOICES_DIR):
        self.stt_model = stt_model
        self.voices_dir = voices_dir
        self._voices: dict[str, object] = {}
        # MLX and the Piper sessions are not meant for concurrent use from many threads.
        self._stt_lock = threading.Lock()
        self._tts_lock = threading.Lock()

    def transcribe(self, audio: np.ndarray, language: str) -> str:
        import mlx_whisper

        if len(audio) < WHISPER_RATE // 4:  # under 0.25 s: nothing was said
            return ""
        with self._stt_lock:
            result = mlx_whisper.transcribe(
                audio,
                path_or_hf_repo=self.stt_model,
                language=language,
                condition_on_previous_text=False,
            )
        return str(result["text"]).strip()

    def _voice(self, name: str):
        from piper import PiperVoice
        from piper.download_voices import download_voice

        if name not in self._voices:
            model = self.voices_dir / f"{name}.onnx"
            if not model.exists() or not model.with_suffix(".onnx.json").exists():
                log.info("downloading Piper voice %s to %s", name, self.voices_dir)
                self.voices_dir.mkdir(parents=True, exist_ok=True)
                download_voice(name, self.voices_dir)
            self._voices[name] = PiperVoice.load(model)
        return self._voices[name]

    def synthesize(self, text: str, voice: str, speed: float) -> bytes:
        from piper import SynthesisConfig

        speed = min(max(speed, 0.5), 1.5)
        with self._tts_lock:
            v = self._voice(voice)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                # length_scale > 1 = slower speech
                v.synthesize_wav(text, w, syn_config=SynthesisConfig(length_scale=1 / speed))
        return buf.getvalue()

    def warm_up(self, voice: str) -> None:
        """Load the models at startup, so the first learner doesn't wait for downloads."""
        self.transcribe(np.zeros(WHISPER_RATE, dtype=np.float32), "it")
        self.synthesize("Ciao!", voice, 1.0)


# --- HTTP --------------------------------------------------------------------


def make_handler(engine: Engine) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "parla-speech"

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, obj: dict) -> None:
            self._send(status, json.dumps(obj, ensure_ascii=False).encode(), "application/json")

        def _body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_UPLOAD:
                raise ValueError("missing or too large request body")
            return self.rfile.read(length)

        def do_GET(self) -> None:  # noqa: N802
            if urlparse(self.path).path == "/health":
                self._json(200, {"ok": True, "stt_model": getattr(engine, "stt_model", None)})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            try:
                if url.path == "/stt":
                    language = parse_qs(url.query).get("language", ["it"])[0]
                    text = engine.transcribe(decode_audio(self._body()), language)
                    self._json(200, {"text": text})
                elif url.path == "/tts":
                    req = json.loads(self._body())
                    text = str(req.get("text", "")).strip()[:MAX_TTS_CHARS]
                    if not text:
                        raise ValueError("empty text")
                    wav = engine.synthesize(text, str(req["voice"]), float(req.get("speed", 1.0)))
                    self._send(200, wav, "audio/wav")
                else:
                    self._json(404, {"error": "not found"})
            except (ValueError, KeyError, wave.Error) as err:
                self._json(400, {"error": str(err)})
            except Exception as err:  # noqa: BLE001 – keep the service alive
                log.exception("request failed")
                self._json(500, {"error": str(err)})

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            log.info("%s %s", self.address_string(), format % args)

    return Handler


def make_server(engine: Engine, host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(engine))


def main() -> None:
    from parla.config import DEFAULT_PAIR, LANGUAGE_PAIRS

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    # 127.0.0.1: only this Mac (and its containers via host.docker.internal) can connect.
    host = os.environ.get("PARLA_SPEECH_BIND", "127.0.0.1")
    engine = LocalEngine()
    server = make_server(engine, host, SPEECH_PORT)
    log.info("loading models (the first start downloads them, ~1.7 GB) …")
    engine.warm_up(LANGUAGE_PAIRS[DEFAULT_PAIR].tts_voice)
    log.info("listening on http://%s:%d", host, SPEECH_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
