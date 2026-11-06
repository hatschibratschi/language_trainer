import threading

import numpy as np
import pytest

from parla import speech
from parla.speech_server import decode_audio, float_to_wav, make_server, resample, wav_to_float


def tone(rate: int, seconds: float = 0.5) -> np.ndarray:
    t = np.arange(int(rate * seconds)) / rate
    return (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


def test_wav_roundtrip_and_resample_to_16k():
    wav = float_to_wav(tone(48_000), 48_000)
    rate, audio = wav_to_float(wav)
    assert rate == 48_000 and np.allclose(audio, tone(48_000), atol=1e-3)
    out = decode_audio(wav)
    assert out.dtype == np.float32 and len(out) == 8_000  # 0.5 s at 16 kHz
    assert resample(audio, 16_000, 16_000).shape == audio.shape


def test_stereo_wav_is_mixed_to_mono():
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(16_000)
        w.writeframes(np.array([1000, 3000] * 100, dtype="<i2").tobytes())
    rate, audio = wav_to_float(buf.getvalue())
    assert rate == 16_000 and len(audio) == 100
    assert np.allclose(audio, 2000 / 32768)


class FakeEngine:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio, language):
        self.calls.append(("stt", len(audio), language))
        return " Vorrei un caffè. "

    def synthesize(self, text, voice, speed):
        self.calls.append(("tts", text, voice, speed))
        return float_to_wav(tone(22_050, 0.1), 22_050)


@pytest.fixture
def server(monkeypatch):
    engine = FakeEngine()
    srv = make_server(engine, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(speech, "SPEECH_HOST", f"http://127.0.0.1:{srv.server_address[1]}")
    yield engine
    srv.shutdown()


def test_client_server_roundtrip(server, tmp_path):
    rec = tmp_path / "rec.wav"
    rec.write_bytes(float_to_wav(tone(44_100), 44_100))
    assert speech.transcribe(rec, "it") == "Vorrei un caffè."
    rate, pcm = speech.wav_to_numpy(speech.synthesize("Ciao!", "it_IT-paola-medium", 0.75))
    assert rate == 22_050 and pcm.dtype == np.int16 and len(pcm) == 2_205
    assert server.calls == [("stt", 8_000, "it"), ("tts", "Ciao!", "it_IT-paola-medium", 0.75)]


def test_bad_request_and_unreachable_service(server, monkeypatch):
    with pytest.raises(speech.SpeechError, match="empty text"):
        speech.synthesize("   ", "it_IT-paola-medium")
    monkeypatch.setattr(speech, "SPEECH_HOST", "http://127.0.0.1:9")
    with pytest.raises(speech.SpeechError, match="nicht erreichbar"):
        speech.synthesize("Ciao", "it_IT-paola-medium", timeout=2)
