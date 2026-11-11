# To do

Open steps after moving the web app to the adventurelog server (2026-11-10).
See "Running on the always-on server" in README.md.

## 1. Mac Mini: serve Ollama and parla-speech over Tailscale

- [x] Ollama listens on `100.72.117.91:11434` (LaunchAgent plist updated)
- [x] parla-speech listens on `100.72.117.91:11500` (agent reinstalled)
- [x] macOS firewall allows incoming connections for ollama and python3.12
      (after `brew upgrade ollama` unblock the new Cellar path again, see README)
- [x] Check from the server (2026-11-11, also from inside the container):
      `ssh adventurelog 'curl -s -m 3 http://100.72.117.91:11434/api/tags; curl -s -m 3 http://100.72.117.91:11500/health'`
- [ ] Note: locally Ollama is now at `100.72.117.91:11434`, no longer at `localhost:11434`
- [ ] Enable auto-login on the Mac so the LaunchAgents come up after switching it on

## 2. Mac Mini: stop the old parla container

- [x] `docker compose down` on the Mac (2026-11-11; the local DB was older than the server's)

## 3. Back up the server database

- [x] `scripts/backup.sh`: nightly upload of `data/parla.db` to the vacanze Nextcloud share
