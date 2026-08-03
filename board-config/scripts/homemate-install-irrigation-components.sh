#!/bin/bash
set -euo pipefail

readonly CONFIG_ROOT="/userdata/hass/config"
readonly COMPONENT_ROOT="${CONFIG_ROOT}/custom_components"
readonly IU_VERSION="2025.12.0"
readonly SMART_VERSION="v2026.7.1"

workdir="$(mktemp -d /tmp/homemate-irrigation-components.XXXXXX)"
trap 'rm -rf -- "${workdir}"' EXIT

curl -fsSL --retry 3 -o "${workdir}/iu.tar.gz" \
  "https://codeload.github.com/rgc99/irrigation_unlimited/tar.gz/refs/tags/${IU_VERSION}"
tar -xzf "${workdir}/iu.tar.gz" -C "${workdir}"

curl -fsSL --retry 3 -o "${workdir}/smart.zip" \
  "https://github.com/altmenorg/HAsmartirrigation/releases/download/${SMART_VERSION}/smart_irrigation.zip"
mkdir "${workdir}/smart"
python3 -m zipfile -e "${workdir}/smart.zip" "${workdir}/smart"

iu_source="${workdir}/irrigation_unlimited-${IU_VERSION}/custom_components/irrigation_unlimited"
smart_source="${workdir}/smart"

python3 - "${iu_source}/manifest.json" "${smart_source}/manifest.json" <<'PY'
import json
import sys

expected = {
    "irrigation_unlimited": "2025.12.0",
    "smart_irrigation": "v2026.7.1",
}
for manifest_path in sys.argv[1:]:
    with open(manifest_path, encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)
    domain = manifest["domain"]
    version = manifest.get("version")
    if expected.get(domain) != version:
        raise SystemExit(f"Unexpected component version: {domain} {version}")
    print(f"Validated {domain} {version}")
PY

/home/forlinx/hass-venv-314/bin/python -m compileall -q \
  "${iu_source}" "${smart_source}"

install -d -m 0755 "${COMPONENT_ROOT}"
stamp="$(date +%Y%m%d-%H%M%S)"

for component in irrigation_unlimited smart_irrigation; do
  target="${COMPONENT_ROOT}/${component}"
  staged="${COMPONENT_ROOT}/.${component}.new-${stamp}"
  [ ! -e "${staged}" ] || {
    echo "Unexpected staging path already exists: ${staged}" >&2
    exit 1
  }
  if [ "${component}" = "irrigation_unlimited" ]; then
    source_path="${iu_source}"
  else
    source_path="${smart_source}"
  fi
  cp -a "${source_path}" "${staged}"
  chown -R forlinx:forlinx "${staged}"
  find "${staged}" -type d -exec chmod 0755 {} +
  find "${staged}" -type f -exec chmod 0644 {} +
  if [ -e "${target}" ]; then
    mv "${target}" "${target}.bak-${stamp}"
  fi
  mv "${staged}" "${target}"
done

/home/forlinx/hass-venv-314/bin/hass --script check_config -c "${CONFIG_ROOT}"
echo "Installed Irrigation Unlimited ${IU_VERSION} and Smart Irrigation ${SMART_VERSION}."
