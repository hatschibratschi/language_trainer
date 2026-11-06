# new features to implement

- the browser says: connection is 'not secure'. why? because we are just locally - then it's ok!
- remove the nation flags in the chat (everywhere).
- voice: give Whisper the tutor's last reply as context (`initial_prompt` in `mlx_whisper.transcribe`,
  passed via `/stt`), so it expects words like *weekend*, *collega*, *fatto*. Test on 2026-11-06:
  beginner speech came out as "Si e Fatoli." / "O parlato molto con il compito con l'hoid."
- voice: tell the tutor when a message was spoken (🎙️ entries have `voice: True`). Then ignore
  spelling, accents and punctuation (a missing "h" in "ho" or "sì" vs. "si" can't be heard), correct
  only grammar and word choice, and if it's unclear, suggest what the learner probably meant instead
  of only "Non ho capito".
- voice: watch for `speak_reply didn't receive enough input values (needed: 3, got: 0)` in
  `docker compose logs` (seen once at 18:24 on 2026-11-06, between two working voice turns,
  maybe Safari reloading the page). Only fix it if it comes back.
- model: `gemma3:27b` is not installed, so the app uses `qwen3:14b`. `ollama pull gemma3:27b`
  (~17 GB) should give better Italian and more reliable corrections.
