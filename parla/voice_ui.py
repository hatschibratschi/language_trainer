"""Voice input in the browser: hold-to-talk and hands-free (injected into the page head).

The browser records the microphone itself (Web Audio), cuts it to 16 kHz mono WAV and hands
it to the server as a data URL; the tutor's spoken reply comes back the same way and is
played here, too. Doing it ourselves (instead of Gradio's audio components) gives

- one button: hold to talk, release to send,
- hands-free: speech is detected by its loudness and sent after a pause,
- reliable playback on the iPhone: the player is unlocked by the first tap, so later
  replies may play without one, and the end of playback is known (hands-free listens again).

The page talks to the server through two hidden components:
#parla-voice-send (clicked when a recording is ready; it fetches it via take()) and the
tutor's audio, passed to play() after every turn.
"""

from __future__ import annotations

VOICE_JS = """
<script>
(() => {
  const RATE = 16000;           // Whisper's sample rate; also keeps uploads small
  const MIN_HOLD_MS = 350;      // shorter presses are taps, not speech
  const MIN_SPEECH_MS = 400;    // hands-free: shorter sounds (a cough, a click) are ignored
  const MAX_MS = 60000;         // a single message is cut off after a minute
  const FLOOR = 0.012;          // hands-free: minimum loudness (RMS) that counts as speech
  const SILENT_WAV = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";

  const S = {
    handsFree: false, pauseMs: 1200,
    // idle | starting | recording | listening | speech | sending | playing
    state: "idle", on: false,       // on: hands-free is running
    ctx: null, stream: null, nodes: [], chunks: [], pre: [], noise: 0,
    t0: 0, lastLoud: 0, released: false, pending: "", flash: "", flashTimer: 0,
    player: null, unlocked: false,
  };

  // --- button label ------------------------------------------------------------
  const LABELS = {
    hold: {
      idle: "🎙️ Halten zum Sprechen", starting: "🎙️ Mikrofon …",
      recording: "🔴 Loslassen zum Senden", sending: "⏳ Wird gesendet …",
      playing: "🎙️ Halten zum Sprechen",
    },
    free: {
      idle: "🎧 Freihändig starten", starting: "🎧 Mikrofon …",
      listening: "👂 Ich höre zu … (tippen = Ende)", speech: "🔴 Du sprichst …",
      sending: "⏳ Tutor denkt nach …", playing: "🔊 Tutor spricht … (tippen = Ende)",
    },
  };
  function ui() {
    const b = document.getElementById("parla-talk");
    if (!b) return;
    const labels = S.handsFree ? LABELS.free : LABELS.hold;
    b.textContent = S.flash || labels[S.state] || labels.idle;
    b.dataset.state = S.state;
    b.classList.toggle("hands-free", S.handsFree);
    b.classList.toggle("active", S.state === "recording" || S.state === "speech");
  }
  function flash(msg) {
    S.flash = msg; ui();
    clearTimeout(S.flashTimer);
    S.flashTimer = setTimeout(() => { S.flash = ""; ui(); }, 2200);
  }

  // --- audio output: one <audio> element, unlocked by the first tap (iOS) ------
  function ensurePlayer() {
    if (!S.player) {
      S.player = new Audio();
      S.player.addEventListener("ended", afterPlay);
      S.player.addEventListener("error", afterPlay);
    }
  }
  function unlock(e) {  // only from a user gesture (event listener or button press)
    if (e && e.isTrusted === false) return;
    if (!S.ctx) S.ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (S.ctx.state === "suspended") S.ctx.resume();
    ensurePlayer();
    if (!S.unlocked) {
      S.unlocked = true;
      S.player.src = SILENT_WAV;
      S.player.play().catch(() => { S.unlocked = false; });
    }
  }
  ["pointerdown", "touchend", "keydown"].forEach((t) =>
    document.addEventListener(t, unlock, { capture: true, passive: true }));

  function stopPlayback() {
    if (S.player && !S.player.paused) S.player.pause();
  }

  // Called after every tutor turn with its audio ("" if nothing is to be spoken).
  function play(dataUrl) {
    if (!dataUrl) { afterPlay(); return; }
    ensurePlayer();
    closeMic();  // hands-free: don't listen to the tutor (and iOS plays louder without mic)
    S.state = "playing"; ui();
    S.player.src = dataUrl;
    S.player.play().catch(() => {
      flash("🔇 Tippe 🔊 zum Anhören");
      afterPlay();
    });
  }
  function afterPlay() {
    if (S.player && S.player.src === SILENT_WAV) return;  // the unlock sound
    if (S.on) listen();
    else if (S.state === "playing" || S.state === "sending") { S.state = "idle"; ui(); }
  }

  // --- microphone ----------------------------------------------------------------
  async function openMic() {
    if (!S.ctx) S.ctx = new (window.AudioContext || window.webkitAudioContext)();
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    closeMic();
    S.stream = stream;
    await S.ctx.resume();
    const src = S.ctx.createMediaStreamSource(stream);
    const proc = S.ctx.createScriptProcessor(4096, 1, 1);
    const mute = S.ctx.createGain();
    mute.gain.value = 0;  // the processor must be connected to run; keep it silent
    proc.onaudioprocess = (e) => onAudio(new Float32Array(e.inputBuffer.getChannelData(0)));
    src.connect(proc); proc.connect(mute); mute.connect(S.ctx.destination);
    S.nodes = [src, proc, mute];
  }
  function closeMic() {
    S.nodes.forEach((n) => { try { n.disconnect(); } catch (_) {} });
    if (S.nodes[1]) S.nodes[1].onaudioprocess = null;
    S.nodes = [];
    if (S.stream) S.stream.getTracks().forEach((t) => t.stop());
    S.stream = null;
  }
  function micError(err) {
    closeMic();
    S.on = false; S.state = "idle";
    const denied = err && (err.name === "NotAllowedError" || err.name === "SecurityError");
    flash(denied ? "🚫 Mikrofon nicht erlaubt" : "🚫 Kein Mikrofon");
    if (!window.isSecureContext) flash("🔒 Mikrofon nur über https");
  }

  function onAudio(buf) {
    const now = performance.now();
    if (S.state === "recording") {
      S.chunks.push(buf);
      if (now - S.t0 > MAX_MS) send();
      return;
    }
    if (S.state !== "listening" && S.state !== "speech") return;
    let sum = 0;
    for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
    const rms = Math.sqrt(sum / buf.length);
    const threshold = Math.max(FLOOR, S.noise * 3);
    if (S.state === "listening") {
      S.noise = S.noise ? S.noise * 0.95 + rms * 0.05 : rms;  // follows the background
      S.pre.push(buf);
      if (S.pre.length > 4) S.pre.shift();  // keep ~0.3 s before the speech starts
      if (rms > threshold) {
        S.state = "speech"; S.chunks = [...S.pre]; S.t0 = now; S.lastLoud = now; ui();
      }
    } else {
      S.chunks.push(buf);
      if (rms > threshold * 0.6) S.lastLoud = now;
      if (now - S.lastLoud > S.pauseMs || now - S.t0 > MAX_MS) {
        if (S.lastLoud - S.t0 < MIN_SPEECH_MS) {  // just a noise: keep listening
          S.state = "listening"; S.chunks = []; ui();
        } else send();
      }
    }
  }

  // --- WAV encoding ------------------------------------------------------------------
  function toWav(chunks, rate) {
    const n = chunks.reduce((a, c) => a + c.length, 0);
    const pcm = new Float32Array(n);
    let o = 0;
    for (const c of chunks) { pcm.set(c, o); o += c.length; }
    const ratio = rate / RATE, m = Math.floor(n / ratio);
    const out = new DataView(new ArrayBuffer(44 + m * 2));
    const str = (p, s) => { for (let i = 0; i < s.length; i++) out.setUint8(p + i, s.charCodeAt(i)); };
    str(0, "RIFF"); out.setUint32(4, 36 + m * 2, true); str(8, "WAVE"); str(12, "fmt ");
    out.setUint32(16, 16, true); out.setUint16(20, 1, true); out.setUint16(22, 1, true);
    out.setUint32(24, RATE, true); out.setUint32(28, RATE * 2, true);
    out.setUint16(32, 2, true); out.setUint16(34, 16, true);
    str(36, "data"); out.setUint32(40, m * 2, true);
    for (let i = 0; i < m; i++) {  // average over each output sample's span (anti-aliasing)
      const a = Math.floor(i * ratio), b = Math.max(a + 1, Math.floor((i + 1) * ratio));
      let s = 0;
      for (let j = a; j < b && j < n; j++) s += pcm[j];
      const v = Math.max(-1, Math.min(1, s / (b - a)));
      out.setInt16(44 + i * 2, v < 0 ? v * 0x8000 : v * 0x7fff, true);
    }
    const bytes = new Uint8Array(out.buffer);
    let bin = "";
    for (let i = 0; i < bytes.length; i += 0x8000)
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return "data:audio/wav;base64," + btoa(bin);
  }

  function send() {
    const chunks = S.chunks, rate = S.ctx.sampleRate;
    S.chunks = []; S.pre = [];
    closeMic();
    S.state = "sending"; ui();
    S.pending = toWav(chunks, rate);
    const b = document.querySelector("#parla-voice-send");
    (b && (b.tagName === "BUTTON" ? b : b.querySelector("button")))?.click();
  }
  function take() { const d = S.pending; S.pending = ""; return d; }

  // --- hold to talk --------------------------------------------------------------------
  async function holdStart() {
    if (S.state === "starting" || S.state === "recording") return;
    stopPlayback();
    S.state = "starting"; S.released = false; ui();
    try { await openMic(); } catch (err) { micError(err); return; }
    if (S.released) {  // let go while the microphone was starting (e.g. permission dialog)
      closeMic(); S.state = "idle"; flash("✅ Bereit – jetzt halten und sprechen");
      return;
    }
    S.state = "recording"; S.chunks = []; S.t0 = performance.now(); ui();
  }
  function holdEnd() {
    if (S.state === "starting") { S.released = true; return; }
    if (S.state !== "recording") return;
    if (performance.now() - S.t0 < MIN_HOLD_MS) {
      closeMic(); S.chunks = []; S.state = "idle"; flash("☝️ Gedrückt halten beim Sprechen");
      return;
    }
    send();
  }

  // --- hands-free ------------------------------------------------------------------------
  async function listen() {
    if (!S.on) return;
    S.state = "starting"; ui();
    try { await openMic(); } catch (err) { micError(err); ui(); return; }
    if (!S.on) { closeMic(); return; }
    S.state = "listening"; S.noise = 0; S.pre = []; S.chunks = []; ui();
  }
  function stop() {
    S.on = false; closeMic(); stopPlayback();
    if (S.state !== "sending") S.state = "idle";
    ui();
  }
  function toggleHandsFree() {
    if (S.on) { stop(); return; }
    S.on = true; stopPlayback(); listen();
  }

  // --- wiring ------------------------------------------------------------------------------
  const talk = (e) => e.target.closest && e.target.closest("#parla-talk");
  document.addEventListener("pointerdown", (e) => {
    const b = talk(e);
    if (!b || e.button > 0) return;
    e.preventDefault();
    if (S.handsFree) { toggleHandsFree(); return; }
    try { b.setPointerCapture(e.pointerId); } catch (_) {}
    holdStart();
  });
  ["pointerup", "pointercancel"].forEach((t) => document.addEventListener(t, (e) => {
    if (!S.handsFree && (talk(e) || S.state === "recording" || S.state === "starting")) holdEnd();
  }));
  document.addEventListener("contextmenu", (e) => { if (talk(e)) e.preventDefault(); });
  // Leaving the chat page or the app ends hands-free listening.
  document.addEventListener("click", (e) => {
    const item = e.target.closest && e.target.closest(".parla-nav-item");
    if (item && item.id !== "parla-nav-chat") stop();
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); });

  window.parlaVoice = {
    take, play, ui,
    configure(handsFree, pauseSeconds) {
      const hf = !!handsFree;
      if (hf !== S.handsFree) stop();
      S.handsFree = hf;
      S.pauseMs = Math.round((Number(pauseSeconds) || 1.2) * 1000);
      ui();
    },
    // Keyboard (⌥R): start/stop instead of holding.
    key() {
      if (S.handsFree) toggleHandsFree();
      else if (S.state === "recording" || S.state === "starting") holdEnd();
      else holdStart();
      return true;
    },
  };
  setTimeout(ui, 0);
})();
</script>
"""
