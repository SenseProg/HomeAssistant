#!/bin/bash
set -euo pipefail

readonly CONFIG_ROOT="/userdata/hass/config"
readonly COMPONENT_ROOT="${CONFIG_ROOT}/custom_components"
readonly BACKUP_ROOT="/userdata/hass/backups/custom_components"
readonly SIKU_VERSION="2.2.6"
readonly SIKU_COMMIT="589b266f5464701c218af554ede135d9edf333e2"
readonly SIKU_ARCHIVE_SHA256="32bb0a9ef3587a3872584a8cd9822cb076d7b1f794a3a4bc4130bd7f5630eabc"

workdir="$(mktemp -d /tmp/homemate-siku.XXXXXX)"
cleanup() {
  case "${workdir}" in
    /tmp/homemate-siku.*) rm -rf -- "${workdir}" ;;
    *) echo "Refusing to remove unexpected path: ${workdir}" >&2 ;;
  esac
}
trap cleanup EXIT

archive="${workdir}/siku.tar.gz"
curl -fsSL --retry 3 -o "${archive}" \
  "https://codeload.github.com/hmn/siku-integration/tar.gz/${SIKU_COMMIT}"
echo "${SIKU_ARCHIVE_SHA256}  ${archive}" | sha256sum --check --status
tar -xzf "${archive}" -C "${workdir}"

source_path="${workdir}/siku-integration-${SIKU_COMMIT}/custom_components/siku"
python3 - "${source_path}/manifest.json" "${SIKU_VERSION}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as manifest_file:
    manifest = json.load(manifest_file)
if manifest.get("domain") != "siku" or manifest.get("version") != sys.argv[2]:
    raise SystemExit(f"Unexpected Siku manifest: {manifest!r}")
print(f"Validated siku {manifest['version']}")
PY

/userdata/hass/venv/bin/python -m compileall -q "${source_path}"

install -d -m 0755 "${COMPONENT_ROOT}"
install -d -o forlinx -g forlinx -m 0755 "${BACKUP_ROOT}"
stamp="$(date +%Y%m%d-%H%M%S)"
target="${COMPONENT_ROOT}/siku"
staged="${COMPONENT_ROOT}/.siku.new-${stamp}"

[ ! -e "${staged}" ] || {
  echo "Unexpected staging path already exists: ${staged}" >&2
  exit 1
}
cp -a "${source_path}" "${staged}"
chown -R forlinx:forlinx "${staged}"
find "${staged}" -type d -exec chmod 0755 {} +
find "${staged}" -type f -exec chmod 0644 {} +

if [ -e "${target}" ]; then
  mv "${target}" "${BACKUP_ROOT}/siku-${stamp}"
fi
mv "${staged}" "${target}"

/userdata/hass/venv/bin/hass --script check_config -c "${CONFIG_ROOT}"
echo "Installed Siku (Blauberg) Fan ${SIKU_VERSION} at ${SIKU_COMMIT}."
