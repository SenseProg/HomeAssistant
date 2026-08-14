#!/bin/bash
# Cloudflare quick tunnel for Home Assistant.
#
# A quick tunnel is account-less, so Cloudflare hands out a NEW random hostname
# every single time cloudflared starts. Nobody can bookmark it. This wrapper
# therefore publishes the current one to two places the moment it appears:
#   /userdata/hass/config/www/cloudflare-url.txt  -> served by HA at
#                                                   /local/cloudflare-url.txt
#   /home/forlinx/cloudflare-url.txt              -> for SSH
# Without that, every reboot silently leaves the tunnel unusable.
set -u
LOG=/tmp/cloudflared.log
WWW=/userdata/hass/config/www/cloudflare-url.txt
HOME_COPY=/home/forlinx/cloudflare-url.txt

: > "$LOG"
/usr/local/bin/cloudflared tunnel --url http://127.0.0.1:8123 --no-autoupdate >> "$LOG" 2>&1 &
CF_PID=$!

for _ in $(seq 1 60); do
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" | head -1)
  [ -n "${URL:-}" ] && break
  sleep 2
done

if [ -n "${URL:-}" ]; then
  STAMP=$(date '+%Y-%m-%d %H:%M:%S')
  printf '%s\nissued: %s\n' "$URL" "$STAMP" > "$WWW" 2>/dev/null
  printf '%s\nissued: %s\n' "$URL" "$STAMP" > "$HOME_COPY"
  logger -t cloudflared-quick "public URL for this run: $URL"
else
  logger -t cloudflared-quick "no URL after 120 s - see $LOG"
fi

wait "$CF_PID"
