# Parla – a local LLM language trainer

Parla is a personal language trainer that runs entirely on your own machine. A local LLM (served by Ollama) acts as a patient tutor you can talk to by text or by voice
(Whisper listens, Piper speaks Italian). The first language pair is **German (native) → Italian (target)**. Other pairs can be added later by changing the configuration.

Nothing leaves the computer. There are no accounts, subscriptions or cloud APIs.

## Quick start

```bash
ollama pull gemma3:27b        # recommended model (qwen3:14b also works)
uv run parla-speech           # speech service (2nd terminal); first start downloads ~1.7 GB
uv run parla                  # opens http://127.0.0.1:7860 in the browser
uv run pytest                 # run tests
```

Choose a model with `PARLA_MODEL=qwen3:14b uv run parla`. Without this setting the app uses the first
installed model from `gemma3:27b`, `mistral-small3.2:24b`, `qwen3:14b`, …

## Running as a web server in Docker (OrbStack)

The app runs in a container. **Ollama** and the speech service **parla-speech** keep running
**natively on the Mac**, because only there do they get Apple-Silicon GPU acceleration (Metal).
The container reaches them via `host.docker.internal`.

```
  iPhone · iPad · Mac browser
         │  https://<mac>.<tailnet>.ts.net:8443   Tailscale HTTPS: text + voice
         │  http://<mac-ip>:7860                  LAN: text only (no mic on iPhone)
┌────────▼──────────────────┐                       ┌─────────────────────────────┐
│ OrbStack container        │   host.docker.        │ Ollama            (native)  │
│ parla  (Gradio web app)   │ ──internal:11434────▶ │ LLM, e.g. gemma3:27b        │
│                           │                       ├─────────────────────────────┤
│ chat · corrections ·      │   host.docker.        │ parla-speech      (native)  │
│ vocabulary · SQLite       │ ──internal:11500────▶ │ STT  Whisper large-v3-turbo │
└───────────────────────────┘                       │ TTS  Piper it_IT-paola      │
                                                    └─────────────────────────────┘
                                                      Mac with Apple Silicon (Metal)
```

```bash
docker compose up -d --build     # build and start (also after code changes)
docker compose logs -f           # view logs
docker compose down              # stop
```

Then open:
- on the Mac: http://localhost:7860
- in the LAN/WLAN: `http://<mac-ip>:7860` (find the IP with `ipconfig getifaddr en0`, currently `192.168.0.145`)

### Configuration (`.env` next to `compose.yaml`)

```bash
PARLA_MODEL=gemma3:27b                      # optional, otherwise chosen automatically
PARLA_USERS=hatschibratschi,bellaMelanto    # learners to choose from (default)
PARLA_AUTH_USER=georg                       # optional: both set → shared password for the app
PARLA_AUTH_PASSWORD=secret
```

The container finds the speech service via `PARLA_SPEECH_HOST` (set in `compose.yaml` to
`http://host.docker.internal:11500`).

After changes: `docker compose up -d`.

### Voice mode (parla-speech)

Speech runs in a second small service on the Mac, next to Ollama:

- **Speech-to-text:** `mlx-whisper` with `whisper-large-v3-turbo` on the Apple GPU (~0.5 s per turn).
- **Text-to-speech:** [Piper](https://github.com/OHF-Voice/piper1-gpl) with the Italian voice `it_IT-paola-medium`.

```bash
uv run parla-speech                   # run in a terminal, or:
scripts/install-speech-agent.sh       # start automatically at login (LaunchAgent)
curl http://localhost:11500/health    # check
```

The first start downloads the Whisper model (~1.6 GB, to `~/.cache/huggingface`) and the voice
(~60 MB, to `~/.local/share/parla/voices`). After that everything works offline. The service only
listens on `127.0.0.1`, so it is not reachable from the LAN (the container still gets through).
Log of the LaunchAgent: `~/Library/Logs/parla-speech.log`; remove it with
`scripts/install-speech-agent.sh --remove`.

**In the app (tab "💬 Gespräch"):**

- **🎙️ Sprechen:** tap to record, speak Italian, tap stop. The transcript appears in the chat
  (marked 🎙️) and goes to the tutor like a typed message. Corrections refer to what Whisper heard.
- The tutor's Italian reply is read aloud (not the German explanations). **🔊 Nochmal anhören**
  plays it again.
- Per user: **🔊 Antworten vorlesen** (on/off) and **🐢 Langsam vorlesen** (75 % speed).

| Setting (speech service) | Default                                   |
|--------------------------|-------------------------------------------|
| `PARLA_SPEECH_PORT`      | `11500`                                   |
| `PARLA_STT_MODEL`        | `mlx-community/whisper-large-v3-turbo`    |
| `PARLA_VOICES_DIR`       | `~/.local/share/parla/voices`             |

Another voice (e.g. the male `it_IT-riccardo-x_low`): change `tts_voice` in `parla/config.py`
([voice samples](https://rhasspy.github.io/piper-samples/)); it is downloaded on first use.

### Using it on the iPhone (HTTPS)

Safari only allows the **microphone** on `https://` pages (or `localhost`). Over
`http://<mac-ip>:7860` the text chat works, but recording does not. Tailscale (already running on
the Mac) provides HTTPS with a valid certificate:

```bash
tailscale serve --bg --https=8443 http://127.0.0.1:7860
tailscale serve status                # shows the URL
```

Then, on the iPhone with the Tailscale app signed in to the same tailnet, open
`https://<mac-name>.<tailnet>.ts.net:8443` (add it to the home screen for an app-like icon).
Port 8443 is used because 443 on this Mac already serves Open WebUI. This is reachable only
inside your tailnet, not from the internet.

Tips for the iPhone:

- The first time you record, Safari asks for microphone permission. If you said no, allow it under
  Settings → Apps → Safari → Microphone (or via the "aA" menu → Website Settings).
- iOS may block autoplay. If the reply isn't spoken automatically, tap ▶ in the **🔊 Tutor**
  player or **🔊 Nochmal anhören**.
- No sound at all? Check the volume and the silent mode switch.

### Users and data

There is no login. Each learner simply picks their name under **"👤 Wer lernt?"**. Each user has their own:

- settings (model, level, scenario, translation option)
- vocabulary list ("Meine Vokabeln"), kept across sessions
- current conversation: you can continue on another device or after a reload

Each browser remembers the last selected user. The user selector is locked while the tutor is
answering. Add learners via `PARLA_USERS` (removing a name only hides it; its data is kept).

The data lives in SQLite at `./data/parla.db` (mounted into the container as `/data`, not in Git).
Back up this file to keep your progress.

### Autostart on macOS

Four parts work together:

1. **Ollama** starts at login (LaunchAgent `com.ollama.server`, already set up).
2. **parla-speech** starts at login (LaunchAgent `com.parla.speech`, installed with
   `scripts/install-speech-agent.sh`; it is restarted automatically if it crashes).
3. **OrbStack** starts at login: `orb config set app.start_at_login true`
   (or OrbStack → Settings → "Start at login").
4. **The container** has `restart: unless-stopped`, so it starts automatically whenever OrbStack starts.
   It only stays off if you stop it explicitly with `docker compose stop`/`down`.

The model list is reloaded on every page load and the speech service is called per request, so the
start order does not matter. `tailscale serve --bg` is remembered by Tailscale across reboots.

### Access in the LAN/WLAN

This works because OrbStack exposes container ports to the LAN (`orb config show` →
`docker.expose_ports_to_lan: true`). Notes:

- **Use only on a trusted home network.** Selecting a user is not a login: anyone in the network can open the app and
  pick any user. A shared password can be set with `PARLA_AUTH_USER`/`PARLA_AUTH_PASSWORD`. For access only from the Mac, set the port in `compose.yaml` to `"127.0.0.1:7860:7860"`.
- If the macOS firewall is on, allow incoming connections for OrbStack.
- Mac asleep = trainer unreachable. If needed, enable System Settings → Battery/Energy →
  "Prevent automatic sleeping when the display is off" (when on power).
- A fixed IP (DHCP reservation in the router) or the Bonjour name (`http://<computer-name>.local:7860`)
  saves you from looking up the IP.
- Ollama and parla-speech stay reachable only on the Mac (`127.0.0.1`), so they are not exposed to the LAN.
- **Voice needs HTTPS** on the iPhone, see [Using it on the iPhone](#using-it-on-the-iphone-https).

**Status:** version 0.3 = roadmap steps 1 and 2: text chat with corrections, level, scenarios,
vocabulary list and trainer, multiple users with stored settings, plus **voice mode**
(push-to-talk with Whisper, Italian replies read aloud by Piper, slow speech option).

## Goals

- Practise **speaking and understanding** Italian in realistic conversations, not just vocabulary drills.
- Get **corrections and explanations in German**, so grammar is clear while you are still a beginner.
- **Adapt to your level** (A1–C1) and remember your typical mistakes and the words you have learned.
- Work **offline and privately** on a Mac (Apple Silicon).

## Core features

### 1. Conversation mode (the core)
- Free conversation or role-play scenarios, for example: *Al bar*, *In albergo*, *Dal medico*, *Chiedere indicazioni*, *Small talk con un collega*.
- The tutor answers in Italian at your level (short sentences and common words at A1/A2).
- After each of your turns the tutor gives a short **correction block**:
  - ✅ the corrected sentence
  - 🇩🇪 a short explanation in German ("*Nach* ‚andare' + Stadt → *a*, nicht *in*")
  - 💡 optionally, a more natural way to say it
- A button shows the German translation of any tutor message.

### 2. Voice mode ✅
- Push-to-talk: you speak Italian, it is transcribed (speech-to-text) and sent to the tutor.
- The tutor's reply is read aloud by an Italian voice (text-to-speech).
- Adjustable speech speed (slow, normal) for beginners.
- *Planned:* **pronunciation feedback**: the transcript is compared with what you meant to say, and words that were transcribed wrongly are flagged as likely pronunciation problems.

### 3. Exercise modes
- **Translation drills:** you get a German sentence, translate it into Italian and receive graded feedback.
- **Vocabulary trainer:** spaced repetition (SM-2 / FSRS) with words taken from your own conversations.
- **Grammar focus:** short targeted exercises (articles, *passato prossimo* vs. *imperfetto*, *congiuntivo*, prepositions) generated for your weak spots.
- **Listening:** the tutor reads a short text aloud and you answer comprehension questions.

### 4. Learner profile and progress
- Level estimate (CEFR) that updates over time.
- Error log grouped by category (gender and articles, verb conjugation, prepositions, word order, …).
- Personal vocabulary list with review status.
- A session summary at the end: new words, main mistakes and a suggestion for next time.

## Architecture

```
┌──────────────────────── Browser (iPhone, iPad, Mac) ───────────────────────┐
│     Chat  ·  Push-to-talk  ·  Tutor voice  ·  Vocabulary trainer           │
└───────────────┬────────────────────────────────────────────▲───────────────┘
                │ text / recording                           │ text / audio
┌───────────────▼──────────── parla  (Gradio, Docker) ───────┴───────────────┐
│  ┌──────────────────┐   ┌──────────────────────┐   ┌─────────────────────┐ │
│  │ Speech client    │   │ Tutor engine         │   │ SQLite              │ │
│  │ parla/speech.py  │   │ prompts, levels,     │   │ users, settings,    │ │
│  └───┬──────────▲───┘   │ correction JSON      │   │ vocab, conversation │ │
│      │          │       └─────┬────────────────┘   └─────────────────────┘ │
└──────┼──────────┼─────────────┼────────────────────────────────────────────┘
       │ audio    │ text, WAV   │ HTTP :11434
┌──────▼──────────┴─────────┐ ┌─▼──────────────────┐
│ parla-speech     :11500   │ │ Ollama             │
│ STT  mlx-whisper (Metal)  │ │ gemma3:27b, …      │
│ TTS  Piper (Italian)      │ │                    │
└───────────────────────────┘ └────────────────────┘
   both native on the Mac (Apple Silicon)
```

A voice turn: record in the browser → `parla-speech /stt` (Whisper, language fixed to Italian) →
the transcript goes to the tutor like a typed message → the reply is shown → `parla-speech /tts`
(Piper) → played in the browser.

- **Tutor engine:** builds the system prompt (language pair, level, scenario) and asks the model for structured output (Ollama `format` = JSON schema) with separate fields for `reply`, `corrections`, `better_phrasing`, `reply_translation` and `new_vocabulary`. This makes it easy to render corrections and fill the vocabulary trainer.
- **Speech service:** `parla/speech_server.py`, a small standard-library HTTP server (`POST /stt`, `POST /tts`, `GET /health`). Uploads that are not WAV (e.g. AAC from an iPhone) are converted with macOS `afconvert`, so no ffmpeg is needed. The container only needs `parla/speech.py`, a plain HTTP client.
- **Storage:** SQLite for users, settings, vocabulary (with trainer boxes) and the current conversation.
- **Language pairs:** defined in `parla/config.py` (`source`, `target`, STT language code, TTS voice), so adding German → Spanish later is mostly configuration.

## Tech stack

| Part            | Choice                                                         |
|-----------------|----------------------------------------------------------------|
| LLM runtime     | Ollama (native on the Mac)                                     |
| LLM             | `gemma3:27b` (main), `qwen3:14b` (fast fallback)               |
| Speech-to-text  | `mlx-whisper` with `whisper-large-v3-turbo` (Apple Silicon)    |
| Text-to-speech  | Piper, voice `it_IT-paola-medium`                              |
| Web app         | Python 3.12, Gradio, `ollama` Python client                    |
| Speech service  | Python standard-library HTTP server, native on the Mac         |
| Database        | SQLite                                                         |
| Deployment      | Docker (OrbStack); HTTPS for the iPhone via `tailscale serve`  |

## Roadmap

1. ✅ **MVP:** text chat with the tutor, level setting and a correction block (Gradio).
2. ✅ **Voice:** push-to-talk with Whisper and Italian TTS.
3. **Memory:** SQLite profile, error log and vocabulary extraction.
4. **Exercises:** translation drills, spaced-repetition vocabulary and grammar focus.
5. **Polish:** web UI, progress dashboard, more scenarios and more language pairs.
