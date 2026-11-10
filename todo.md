# To do

Open steps after moving the web app to the adventurelog server (2026-11-10).
See "Running on the always-on server" in README.md.

## 1. Mac Mini: serve Ollama and parla-speech over Tailscale

Both still listen on localhost only, so the server shows "💤 Mac Mini nicht erreichbar".
Bind them to the Mac's Tailscale IP (not `0.0.0.0`, so the home LAN can't reach them):

```bash
sed -i '' 's#127.0.0.1:11434#100.72.117.91:11434#' ~/Library/LaunchAgents/com.ollama.server.plist
launchctl bootout gui/$(id -u)/com.ollama.server
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ollama.server.plist
PARLA_SPEECH_BIND=100.72.117.91 scripts/install-speech-agent.sh
```

- [ ] Ollama listens on `100.72.117.91:11434`
- [ ] parla-speech listens on `100.72.117.91:11500`
- [ ] If the macOS firewall asks: allow incoming connections
- [ ] Check from the server:
      `ssh adventurelog 'curl -s -m 3 http://100.72.117.91:11434/api/tags; curl -s -m 3 http://100.72.117.91:11500/health'`
- [ ] Note: locally Ollama is then at `100.72.117.91:11434`, no longer at `localhost:11434`
- [ ] Both start via LaunchAgents at login → enable auto-login on the Mac so they come up
      after switching it on

## 2. Mac Mini: stop the old parla container

Otherwise there are two databases that drift apart. The server's copy is from
2026-11-10 18:11; the server is now the source of truth.

- [ ] `docker compose down` in this repo on the Mac

## 3. Optional: back up the server database

- [ ] Nightly backup of `data/parla.db` to Nextcloud, like `~/git/github/vacanze/backup.sh`
      (use `sqlite3 .backup` for a consistent copy, cron on the server)
