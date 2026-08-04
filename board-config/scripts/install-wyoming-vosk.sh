#!/usr/bin/env bash
set -euo pipefail

readonly SOURCE_DIR=/home/forlinx/wyoming-vosk
readonly PYTHON=/home/forlinx/hass-venv-314/bin/python
readonly VENV_DIR=/home/forlinx/wyoming-vosk-venv-314
readonly DATA_DIR=/home/forlinx/wyoming-vosk-data
readonly SENTENCES_DIR=/home/forlinx/wyoming-vosk-sentences
readonly REPOSITORY=https://github.com/rhasspy/wyoming-vosk.git
readonly REVISION=335a4744d2d0d67624386338e8656f40a3294626

if [[ -e "$SOURCE_DIR" ]]; then
  if [[ ! -d "$SOURCE_DIR/.git" ]]; then
    echo "Refusing to replace non-git path: $SOURCE_DIR" >&2
    exit 1
  fi
  current_revision="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
  if [[ "$current_revision" != "$REVISION" ]]; then
    echo "Unexpected source revision: $current_revision" >&2
    exit 1
  fi
else
  git clone "$REPOSITORY" "$SOURCE_DIR"
  git -C "$SOURCE_DIR" checkout --detach "$REVISION"
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "Required Python interpreter is missing: $PYTHON" >&2
  exit 1
fi

"$PYTHON" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install "$SOURCE_DIR"
install -d -m 0755 "$DATA_DIR"
install -d -m 0755 "$SENTENCES_DIR"

PYTHONPATH="$SOURCE_DIR" "$VENV_DIR/bin/python" - "$DATA_DIR" <<'PY'
import sys
from pathlib import Path

from wyoming_vosk.download import download_model

data_dir = Path(sys.argv[1])
model_name = "vosk-model-small-uk-v3-small"
model_dir = data_dir / model_name
if not model_dir.is_dir():
    download_model("uk", model_name, data_dir)
print(model_dir)
PY

echo "Wyoming Vosk is installed. Install and enable board-config/systemd/wyoming-vosk.service next."
