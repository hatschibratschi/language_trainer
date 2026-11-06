# Parla – a local LLM language trainer

Parla is a personal language trainer that runs entirely on your own machine. A local LLM (served by Ollama) acts as a patient tutor you can talk to by text or by voice. The first language pair is **German (native) → Italian (target)**. Other pairs can be added later by changing the configuration.

Nothing leaves the computer. There are no accounts, subscriptions or cloud APIs.

## Quick start

```bash
ollama pull gemma3:27b        # recommended model (qwen3:14b also works)
uv run parla                  # opens http://127.0.0.1:7860 in the browser
uv run pytest                 # run tests
```

Choose a model with `PARLA_MODEL=qwen3:14b uv run parla`. Without this setting the app uses the first
installed model from `gemma3:27b`, `mistral-small3.2:24b`, `qwen3:14b`, …

## Running as a web server in Docker (OrbStack)

The app runs in a container. Ollama keeps running **natively on the Mac**, because only there does it
get Apple-Silicon GPU acceleration (Metal). The container reaches it via `host.docker.internal:11434`.

```
 Browser (Mac, iPhone, iPad, laptop …)
        │  http://<mac-ip>:7860
 ┌──────▼──────────────┐        ┌─────────────────────────┐
 │ OrbStack container  │ ─────▶ │ Ollama (native, macOS)  │
 │ parla (Gradio)      │  host.docker.internal:11434      │
 └─────────────────────┘        └─────────────────────────┘
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

After changes: `docker compose up -d`.

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

Three parts work together; no extra LaunchAgent is needed:

1. **Ollama** starts at login (LaunchAgent `com.ollama.server`, already set up).
2. **OrbStack** starts at login: `orb config set app.start_at_login true`
   (or OrbStack → Settings → "Start at login").
3. **The container** has `restart: unless-stopped`, so it starts automatically whenever OrbStack starts.
   It only stays off if you stop it explicitly with `docker compose stop`/`down`.

The model list is reloaded on every page load, so it does not matter whether Ollama or the container
comes up first.

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
- Ollama itself stays reachable only on the Mac (`127.0.0.1`), so it is not exposed to the LAN.
- **For later (voice mode):** browsers allow microphone access only via `localhost` or **HTTPS**.
  For voice from an iPhone you will need HTTPS, e.g. via Tailscale (`tailscale serve`) or a
  reverse proxy such as Caddy.

**Status:** version 0.2 = roadmap step 1 (text chat with corrections, level, scenarios, vocabulary list)
plus multiple users with stored settings, vocabulary and conversation.

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

### 2. Voice mode
- Push-to-talk: you speak Italian, it is transcribed (speech-to-text) and sent to the tutor.
- The tutor's reply is read aloud by an Italian voice (text-to-speech).
- Optional **pronunciation feedback**: the transcript is compared with what you meant to say, and words that were transcribed wrongly are flagged as likely pronunciation problems.
- Adjustable speech speed (slow, normal) for beginners.

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
┌────────────────────────── Frontend (Web UI) ──────────────────────────┐
│  Chat view · Push-to-talk · Exercise views · Progress dashboard       │
└───────────────┬───────────────────────────────────────▲───────────────┘
                │ text / audio                          │ text / audio
┌───────────────▼───────────────────────────────────────┴───────────────┐
│                       Backend (Python, FastAPI)                        │
│  ┌──────────┐   ┌──────────────────┐   ┌──────────┐   ┌────────────┐  │
│  │   STT    │──▶│ Tutor engine     │──▶│   TTS    │   │  SQLite    │  │
│  │ (Whisper)│   │ prompts, levels, │   │ (Kokoro/ │   │ profile,   │  │
│  └──────────┘   │ correction JSON  │   │  Piper)  │   │ vocab, SRS │  │
│                 └────────┬─────────┘   └──────────┘   └────────────┘  │
└──────────────────────────┼────────────────────────────────────────────┘
                           │ HTTP (localhost:11434)
                    ┌──────▼──────┐
                    │   Ollama    │  LLM (e.g. gemma3:27b)
                    └─────────────┘
```

- **Tutor engine:** builds the system prompt (language pair, level, scenario, known mistakes) and asks the model for structured output (Ollama `format` = JSON schema) with separate fields for `reply`, `corrections`, `explanation_de` and `new_vocabulary`. This makes it easy to render corrections and fill the vocabulary trainer.
- **Storage:** SQLite for the learner profile, error log, vocabulary and spaced-repetition state.
- **Language pairs:** defined in a config file (`source: de`, `target: it`, TTS voice, STT language code), so adding German → Spanish later is mostly configuration.

## Tech stack (proposed)

| Part            | Choice                                                   |
|-----------------|----------------------------------------------------------|
| LLM runtime     | Ollama (already installed)                               |
| LLM             | `gemma3:27b` (main), `qwen3:14b` (fast fallback)         |
| Speech-to-text  | `mlx-whisper` with `whisper-large-v3-turbo` (Apple Silicon) |
| Text-to-speech  | Kokoro-82M (Italian voices), fallback: macOS `say` / Piper |
| Backend         | Python 3.12, FastAPI, `ollama` Python client             |
| Frontend        | Simple web UI (HTML + HTMX or React), or Gradio for a prototype |
| Database        | SQLite                                                   |

## Roadmap

1. **MVP:** text chat with the tutor, level setting and a correction block (CLI or Gradio).
2. **Voice:** push-to-talk with Whisper and Italian TTS.
3. **Memory:** SQLite profile, error log and vocabulary extraction.
4. **Exercises:** translation drills, spaced-repetition vocabulary and grammar focus.
5. **Polish:** web UI, progress dashboard, more scenarios and more language pairs.
