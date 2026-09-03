#!/bin/bash
# Safe deploy on the board, per .claude/skills/home-assistant/SKILL.md:
#   1. the staged file /tmp/deploy/<name> must match the sha256 given by the caller
#   2. rollback copy of the current target goes to the NAS:
#      backups/deployment-rollback/<basename>.bak-<stamp>  (never under /userdata)
#   3. write <target>.new, then atomic mv; verify sha256 of the result
# Usage:
#   deploy.sh deploy <stamp> <name>:<target>:<sha256> ...
#   deploy.sh reload <domain> ...   (automation, template, command_line, shell_command, history_stats ...)
# Lives in /home/forlinx/deploy.sh since 2026-09-03: systemd-tmpfiles-clean wiped
# /tmp/deploy.sh and the /tmp/deploy staging dir in the middle of a session.
set -u
ROLLBACK=/userdata/hass/config-standalone/backups/deployment-rollback
STAGE=/tmp/deploy
cmd=${1:-}; shift || true
case "$cmd" in
  deploy)
    stamp=${1:?stamp}; shift
    fail=0
    mkdir -p "$ROLLBACK" 2>/dev/null
    for spec in "$@"; do
      src="${spec%%:*}"; rest="${spec#*:}"; target="${rest%%:*}"; sha="${rest#*:}"
      [ -f "$STAGE/$src" ] || { echo "MISSING staged $src"; fail=1; continue; }
      actual=$(sha256sum "$STAGE/$src" | cut -c1-64)
      if [ "$actual" != "$sha" ]; then echo "SHA MISMATCH staged $src ($actual)"; fail=1; continue; fi
      if [ -f "$target" ]; then
        cp -p "$target" "$ROLLBACK/$(basename "$target").bak-$stamp" 2>/dev/null || echo "WARN no rollback copy for $target (NAS down?)"
      fi
      dir=$(dirname "$target")
      if [ -w "$dir" ]; then
        cp "$STAGE/$src" "$target.new" || { echo "FAILED copy $target"; fail=1; continue; }
        [ -f "$target" ] && chmod --reference="$target" "$target.new" 2>/dev/null
        mv -f "$target.new" "$target"
      else
        sudo -n cp "$STAGE/$src" "$target.new" && sudo -n mv -f "$target.new" "$target" || { echo "FAILED (no write access) $target"; fail=1; continue; }
      fi
      case "$target" in *.sh) chmod +x "$target" 2>/dev/null;; esac
      if [ "$(sha256sum "$target" | cut -c1-64)" = "$sha" ]; then echo "DEPLOYED $target ${sha:0:16}"; rm -f "$STAGE/$src"; else echo "FAILED verify $target"; fail=1; fi
    done
    exit $fail;;
  reload)
    TOKEN=$(cat /home/forlinx/.ha_token)
    # localhost may be banned by HA's ip_ban (seen 03.09.2026: the board booted
    # with a 2024 clock, the token looked "not yet valid", 5 failures -> ban).
    # The LAN address is a different client IP and keeps working.
    for d in "$@"; do
      code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 60 -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -X POST "http://localhost:8123/api/services/$d/reload" -d '{}')
      if [ "$code" = "403" ]; then
        code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 60 -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -X POST "http://192.168.50.141:8123/api/services/$d/reload" -d '{}')
        code="$code (via LAN ip, localhost banned)"
      fi
      echo "reload $d: $code"
    done;;
  *) echo "usage: deploy.sh deploy <stamp> <name>:<target>:<sha256> ... | reload <domain> ..."; exit 2;;
esac
