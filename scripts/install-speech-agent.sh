#!/bin/sh
# Install (or update) a LaunchAgent that starts parla-speech at login and keeps it running.
# Usage: scripts/install-speech-agent.sh            install / restart
#        scripts/install-speech-agent.sh --remove   uninstall
set -eu

LABEL=com.parla.speech
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
REPO=$(cd "$(dirname "$0")/.." && pwd)
UV=$(command -v uv || true)
LOG="$HOME/Library/Logs/parla-speech.log"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true

if [ "${1:-}" = "--remove" ]; then
    rm -f "$PLIST"
    echo "Removed $LABEL."
    exit 0
fi

[ -n "$UV" ] || { echo "uv not found in PATH" >&2; exit 1; }

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$UV</string><string>run</string><string>--project</string><string>$REPO</string>
        <string>parla-speech</string>
    </array>
    <key>WorkingDirectory</key><string>$REPO</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$LOG</string>
    <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
PLIST

launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed $LABEL (log: $LOG). Check: curl http://localhost:11500/health"
