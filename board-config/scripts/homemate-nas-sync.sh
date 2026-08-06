#!/bin/bash
set -euo pipefail

readonly NAS_SHARE="//192.168.50.25/HomeAssistant"
readonly NAS_CREDENTIALS="/etc/samba/credentials/homeassistant-backup"
readonly NAS_ROOT="MB35x8"
readonly STATE_DIR="/var/lib/homemate-nas-sync"
readonly CURSOR_FILE="${STATE_DIR}/journal.cursor"

run_smb() {
  local output

  # smbclient sometimes exits 0 even when an individual command reports an
  # NT_STATUS_* error, so both the process status and its output are checked.
  if ! output="$(/usr/bin/smbclient "${NAS_SHARE}" -A "${NAS_CREDENTIALS}" -c "$1" 2>&1)"; then
    printf '%s\n' "${output}" >&2
    return 1
  fi
  if /usr/bin/grep -q 'NT_STATUS_' <<<"${output}"; then
    printf '%s\n' "${output}" >&2
    return 1
  fi
  printf '%s\n' "${output}"
}

# The vendor kernel has neither CIFS nor autofs support, so use Samba's
# userspace client instead of a kernel mount. Verify every directory after
# creation so an authentication or network failure cannot be ignored.
if ! run_smb "cd \"${NAS_ROOT}\"; ls" >/dev/null 2>&1; then
  run_smb "mkdir \"${NAS_ROOT}\"" >/dev/null
fi
if ! run_smb "cd \"${NAS_ROOT}/journals\"; ls" >/dev/null 2>&1; then
  run_smb "cd \"${NAS_ROOT}\"; mkdir \"journals\"" >/dev/null
fi

# Backups are deliberately not handled here. Home Assistant must write them
# directly to a remote backup location; staging archives under /userdata made
# the small eMMC partition fill up and recursively enlarged later backups.

# Export new journal entries since the last successful NAS upload. The cursor
# advances only after the compressed log reaches the NAS, so a network failure
# is retried without losing evidence. If an old cursor has already been
# vacuumed, fall back to the last 24 hours and establish a fresh cursor.
/usr/bin/install -d -m 0700 "${STATE_DIR}"
readonly RUN_STAMP="$(/usr/bin/date +%F_%H%M%S)"
readonly LOG_RAW="$(/usr/bin/mktemp "/tmp/homemate-system-${RUN_STAMP}.XXXXXX.log")"
readonly LOG_TEMP="${LOG_RAW}.gz"
trap '/usr/bin/rm -f -- "${LOG_RAW}" "${LOG_TEMP}"' EXIT

if [[ -s "${CURSOR_FILE}" ]]; then
  old_cursor="$(<"${CURSOR_FILE}")"
  if ! /usr/bin/journalctl --after-cursor "${old_cursor}" \
    --output=short-iso --show-cursor --no-pager > "${LOG_RAW}"; then
    /usr/bin/journalctl --since '24 hours ago' \
      --output=short-iso --show-cursor --no-pager > "${LOG_RAW}"
  fi
else
  /usr/bin/journalctl --since '24 hours ago' \
    --output=short-iso --show-cursor --no-pager > "${LOG_RAW}"
fi

cursor_line="$(/usr/bin/tail -n 1 "${LOG_RAW}")"
if [[ "${cursor_line}" != '-- cursor: '* ]]; then
  echo "journalctl did not return a cursor" >&2
  exit 1
fi
new_cursor="${cursor_line#-- cursor: }"
entry_count="$(/usr/bin/grep -vc '^-- cursor: ' "${LOG_RAW}" || true)"

if (( entry_count > 0 )); then
  readonly LOG_TARGET="${NAS_ROOT}/journals/system-${RUN_STAMP}.log.gz"
  /usr/bin/grep -v '^-- cursor: ' "${LOG_RAW}" | /usr/bin/gzip -9 > "${LOG_TEMP}"
  /usr/bin/chmod 0640 "${LOG_TEMP}"
  run_smb "put \"${LOG_TEMP}\" \"${LOG_TARGET}\""
fi

printf '%s\n' "${new_cursor}" > "${CURSOR_FILE}.new"
/usr/bin/chmod 0600 "${CURSOR_FILE}.new"
/usr/bin/mv -- "${CURSOR_FILE}.new" "${CURSOR_FILE}"
/usr/bin/rm -f -- "${LOG_RAW}" "${LOG_TEMP}"
trap - EXIT
