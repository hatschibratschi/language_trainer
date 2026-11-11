#!/bin/sh
# Back up data/parla.db as a gzipped copy into a Nextcloud share (same share as the vacanze blog).
# Skips the upload when nothing changed since the last backup. Run on the server, e.g. from cron:
#   45 3 * * * ~/git/github/language_trainer/scripts/backup.sh >> ~/git/github/language_trainer/backup.log 2>&1
# Needs NEXTCLOUD_SHARE_URL (and NEXTCLOUD_SHARE_PASSWORD if the share has one) in .env.
# The share must allow "upload and editing" so old backups can be listed and deleted.

set -eu
cd "$(dirname "$0")/.."

NEXTCLOUD_SHARE_URL=$(sed -n 's/^NEXTCLOUD_SHARE_URL=//p' .env)
NEXTCLOUD_SHARE_PASSWORD=$(sed -n 's/^NEXTCLOUD_SHARE_PASSWORD=//p' .env)
if [ -z "$NEXTCLOUD_SHARE_URL" ]; then
  echo "!! Set NEXTCLOUD_SHARE_URL in .env, e.g. https://cloud.example.org/s/AbCdEf123" >&2
  exit 1
fi
# https://host/s/TOKEN → host and TOKEN
host=${NEXTCLOUD_SHARE_URL%%/s/*}
host=${host%/index.php}
token=${NEXTCLOUD_SHARE_URL##*/s/}
token=${token%%[/?#]*}

tmp=$(mktemp -d)
response="$tmp/response"
trap 'rm -rf "$tmp"' EXIT

# Consistent snapshot even while the app writes (SQLite online backup API).
python3 -c 'import sqlite3, sys
src = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close()' data/parla.db "$tmp/parla.db"

state=.backup-state
fingerprint=$(md5sum "$tmp/parla.db" | cut -d' ' -f1)
if [ -f "$state" ] && [ "$(cat "$state")" = "$fingerprint" ]; then
  echo "$(date '+%F %T') no changes, skipped"
  exit 0
fi

name="parla-$(date '+%Y%m%d-%H%M').db.gz"
gzip -n -c "$tmp/parla.db" > "$tmp/$name"

# Public share WebDAV (Nextcloud 29+). A share password goes in as user "anonymous".
dav="$host/public.php/dav/files/$token"
nc() { curl -sS ${NEXTCLOUD_SHARE_PASSWORD:+-u "anonymous:$NEXTCLOUD_SHARE_PASSWORD"} -H 'X-Requested-With: XMLHttpRequest' "$@"; }

status=$(nc -o "$response" -w '%{http_code}' -T "$tmp/$name" "$dav/$name")
case "$status" in
  2*) echo "$fingerprint" > "$state"
      echo "$(date '+%F %T') uploaded $name ($(du -h "$tmp/$name" | cut -f1))" ;;
  *)  echo "!! $(date '+%F %T') upload of $name to $host failed: HTTP $status" >&2
      sed -n 's/.*<s:message>\(.*\)<\/s:message>.*/   \1/p' "$response" >&2
      exit 1 ;;
esac

# Keep the newest $keep backups; the dated names sort oldest first.
keep=40
nc -X PROPFIND -H 'Depth: 1' "$dav/" \
  | grep -oE 'parla-[0-9]{8}-[0-9]{4}\.db\.gz' | sort -u \
  | awk -v keep="$keep" '{ f[NR] = $0 } END { for (i = 1; i <= NR - keep; i++) print f[i] }' \
  | while read -r old; do
      nc -o /dev/null -X DELETE "$dav/$old" && echo "$(date '+%F %T') deleted $old"
    done
