# Parla – a local LLM language trainer

> **📱 iPhone / voice: open <https://mac-mini.tailc86229.ts.net:8443>**
> (Tailscale must be on). Don't use `http://192.168…:7860`: Safari blocks the microphone there.

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

## Running on the always-on server (adventurelog)

The web app and the SQLite database live on the server, so the **vocabulary trainer and
list editor work around the clock**. The Mac Mini is only switched on for the chat:
it serves Ollama and parla-speech to the server over Tailscale.

```
  iPhone · iPad · browser
         │  https://parla.178-104-161-250.sslip.io   (Caddy, password)
┌────────▼──────────────────────────┐   Tailscale    ┌──────────────────────────┐
│ adventurelog server (always on)   │ ─────────────▶ │ Mac Mini (on when needed)│
│ parla container + SQLite          │  :11434 :11500 │ Ollama · parla-speech    │
│ trainer · list editor · settings  │                └──────────────────────────┘
│ chat · lookup · voice ── need the Mac
└───────────────────────────────────┘
```

While the Mac is off, chat and lookup show a "💤 Mac Mini nicht erreichbar" banner and
the app opens on the vocabulary trainer. Every 15 s the app checks again; once the Mac is
up, the banner disappears and the conversation starts.

**Mac:** Ollama and parla-speech must listen on the Tailscale address, not only on
localhost: in `~/Library/LaunchAgents/com.ollama.server.plist` set `OLLAMA_HOST` to
`100.72.117.91:11434` (or `0.0.0.0:11434`), and install the speech agent with
`PARLA_SPEECH_BIND=100.72.117.91 scripts/install-speech-agent.sh`. The macOS firewall must
allow incoming connections for both binaries (the real paths, not the symlinks):

```bash
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp "$(realpath /opt/homebrew/bin/ollama)"
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp "$(realpath .venv/bin/python)"
```

After `brew upgrade ollama` the Cellar path changes, so run the first line again.

**Server** (`~/git/github/language_trainer`, `.env` as described in `compose.server.yaml`):

```bash
git pull && docker compose up -d --build
```

Caddy (`~/adventurelog/caddy/Caddyfile`) has `parla.178-104-161-250.sslip.io { reverse_proxy parla:7860 }`.

**Backup:** `scripts/backup.sh` uploads a consistent copy of `data/parla.db`
(`parla-YYYYMMDD-HHMM.db.gz`, newest 40 kept) to the same Nextcloud share as the vacanze
blog; it needs `NEXTCLOUD_SHARE_URL` / `NEXTCLOUD_SHARE_PASSWORD` in `.env`. Cron on the server:
`45 3 * * * ~/git/github/language_trainer/scripts/backup.sh >> ~/git/github/language_trainer/backup.log 2>&1`

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

**In the app (page "💬 Gespräch"):**

- **🎙️ Halten zum Sprechen** (default): hold the button while you speak Italian, let go to
  send. The button turns red while it records; on the very first press wait for that (Safari
  asks for the microphone first). The transcript appears in the chat
  (marked 🎙️) and goes to the tutor like a typed message. Whisper gets the tutor's last reply
  as context (`initial_prompt`), so it expects the words of the conversation.
- The tutor knows which messages were spoken: there it ignores spelling, accents and punctuation
  (they can't be heard, e.g. "o"/"ho", "si"/"sì"), corrects only grammar and word choice, and if
  the transcript is unclear it suggests what you probably meant.
- **🎧 Freihändig** (choose it under ⚙️ Einstellungen → Sprechen): tap the button once and just
  talk. A pause (default 1.2 s, adjustable) sends what you said; while the tutor answers and
  speaks the microphone is off, then it listens again (green button). Tap again to end; leaving
  the chat page or locking the phone ends it, too. Short noises are ignored, and so are the
  phrases Whisper tends to invent from background noise ("Grazie per la visione", "Sottotitoli
  …"). For thinking pauses, raise the pause in the settings.
- The tutor's Italian reply is read aloud (not the German explanations). The **🔊** button next
  to the talk button plays it again.
- Words the tutor picks as new vocabulary are shown under its reply (📚) and saved to the
  "Standard" list.
- Under **⚙️ Einstellungen**, per user: **🔊 Antworten vorlesen** (on/off) and
  **🐢 Langsam vorlesen** (75 % speed), the speaking mode and the hands-free pause.

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

- The first time you press the talk button, Safari asks for microphone permission. If you said no, allow it under
  Settings → Apps → Safari → Microphone (or via the "aA" menu → Website Settings).
- Safari only plays sound after a first tap on the page, so the tutor's greeting right after
  opening the app may stay silent (the button briefly shows "🔇 Tippe 🔊 zum Anhören"). From
  the first tap on, replies are spoken automatically.
- No sound at all? Check the volume and the silent mode switch.

### Layout: burger menu and settings

The app is laid out for the phone. The **☰** menu at the top left switches between the pages
💬 Gespräch, 🗂️ Vokabeltrainer, 🔎 Nachschlagen, ✏️ Listen bearbeiten and ⚙️ Einstellungen.
The chat page holds only the conversation, the talk button with **🔊** (replay) and the text field;
**🔄 Neu** in the header starts a new conversation. Everything else is on **⚙️ Einstellungen**:
the learner ("👤 Wer lernt?"), level, scenario, read-aloud options, translation option, model
and the keyboard shortcuts.

### Vocabulary: trainer, lookup and list editor

- **🗂️ Vokabeltrainer:** Leitner box with 6 boxes ("Fächer"); rounds of 10 words, mostly from
  the low boxes.
- **🔎 Nachschlagen:** type one or more words (German or Italian, separated by commas). The
  model returns 2–4 meanings per word with CEFR level (difficulty) and an example sentence, and
  marks words you already have. Tick the ones you want, pick a list (a new name creates a new
  list) and the box (1 = new/hard … 6 = known), then **💾 Ausgewählte speichern**.
- **✏️ Listen bearbeiten:** an editable table per list. Change words, translations, list (moves
  the word) and box; empty the Italian word to delete it; add rows via the cell menu. Nothing
  is written until **💾 Speichern**. Lists can be renamed or merged.

### Keyboard shortcuts

⌥ = Alt/Option. They are listed in the app under **⌨️ Tastenkürzel**.

| Key | Action |
|---|---|
| ⌥1 … ⌥5 | switch page (Gespräch, Trainer, Nachschlagen, Listen, Einstellungen) |
| ⌥R | start/stop recording (stop = send); hands-free: on/off |
| ⌥P | play the last reply again |
| ⌥T | show/hide the translation of the last reply |
| Esc / `/` | leave the text field / jump into the message field |
| Space | trainer: reveal (or start a new round) |
| ← or 1 / → or 2 | trainer: not known / known |
| N | trainer: new round |

Single keys only work when no text field has the focus.

### Users and data

There is no login. Each learner simply picks their name under **⚙️ Einstellungen →
"👤 Wer lernt?"**. Each user has their own:

- settings (model, level, scenario, translation option)
- vocabulary lists, kept across sessions
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
- The browser shows **"Not secure"** for `http://` addresses. That is expected and fine here:
  the traffic stays in your own network. Only a shared password (`PARLA_AUTH_PASSWORD`) would
  travel unencrypted. The microphone, though, needs HTTPS (or `localhost`).

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
  - a short explanation in German ("*Nach* ‚andare' + Stadt → *a*, nicht *in*")
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

A voice turn: the browser records the microphone itself (Web Audio, `parla/voice_ui.py`; in
hands-free mode it also detects speech and pauses by loudness) and sends 16 kHz WAV → `parla-speech /stt` (Whisper, language fixed to Italian) →
the transcript goes to the tutor like a typed message → the reply is shown → `parla-speech /tts`
(Piper) → sent back as a data URL and played by the same script (which then, hands-free,
listens again).

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
