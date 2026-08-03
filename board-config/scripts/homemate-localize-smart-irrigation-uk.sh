#!/bin/bash
set -euo pipefail

readonly CONFIG_ROOT="/userdata/hass/config"
readonly COMPONENT_ROOT="${CONFIG_ROOT}/custom_components/smart_irrigation"
readonly BACKUP_ROOT="/userdata/hass/backups/custom_components"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly OVERLAY_SCRIPT="${SCRIPT_DIR}/localize-smart-irrigation-uk.py"

[ -d "${COMPONENT_ROOT}" ] || {
  echo "Smart Irrigation is not installed at ${COMPONENT_ROOT}" >&2
  exit 1
}
[ -f "${OVERLAY_SCRIPT}" ] || {
  echo "Missing overlay helper: ${OVERLAY_SCRIPT}" >&2
  exit 1
}

stamp="$(date +%Y%m%d-%H%M%S)"
install -d -o forlinx -g forlinx -m 0755 "${BACKUP_ROOT}"
backup="${BACKUP_ROOT}/smart_irrigation-uk-${stamp}"
cp -a "${COMPONENT_ROOT}" "${backup}"

rollback() {
  if [ -d "${backup}" ]; then
    rm -rf -- "${COMPONENT_ROOT}"
    cp -a "${backup}" "${COMPONENT_ROOT}"
    echo "Restored Smart Irrigation from ${backup}" >&2
  fi
}
trap rollback ERR

python3 "${OVERLAY_SCRIPT}" "${COMPONENT_ROOT}"
chown -R forlinx:forlinx "${COMPONENT_ROOT}"
find "${COMPONENT_ROOT}" -type d -exec chmod 0755 {} +
find "${COMPONENT_ROOT}" -type f -exec chmod 0644 {} +
/home/forlinx/hass-venv-314/bin/python -m compileall -q "${COMPONENT_ROOT}"
/home/forlinx/hass-venv-314/bin/hass --script check_config -c "${CONFIG_ROOT}"

trap - ERR
sudo systemctl restart home-assistant

echo "Installed Ukrainian Smart Irrigation overlay. Backup: ${backup}"
