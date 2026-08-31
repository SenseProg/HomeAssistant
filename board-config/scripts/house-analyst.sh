#!/bin/bash
# Daily read-only Home Assistant analysis through Claude Code subscription auth.

set -uo pipefail

HA="http://localhost:8123"
TOKEN_FILE="/home/forlinx/.ha_token"
OUT_DIR="/userdata/hass/config/www/analyst"
OUT_JSON="$OUT_DIR/latest.json"
OUT_MD="$OUT_DIR/latest.md"
LOG="/home/forlinx/house-analyst/analyze.log"

mkdir -p "$OUT_DIR" "$(dirname "$LOG")"
exec 2>>"$LOG"
echo "=== $(date -Is) старт ===" >>"$LOG"

if [ ! -r "$TOKEN_FILE" ]; then
  echo "немає $TOKEN_FILE" >>"$LOG"
  exit 1
fi
TOKEN=$(cat "$TOKEN_FILE")

CONTEXT=$(/userdata/hass/venv/bin/python - "$HA" "$TOKEN" <<'PY'
import json
import sys
import urllib.request

ha, tok = sys.argv[1], sys.argv[2]


def get(path):
    request = urllib.request.Request(ha + path)
    request.add_header("Authorization", "Bearer " + tok)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


KEEP_PREFIX = (
    "sensor.zagalne_navantazhennia", "sensor.zagalnii_strum",
    "sensor.energy_meter_total_energy", "sensor.tarif_elektroenergii",
    "sensor.boiler_", "sensor.terneo_", "sensor.nasos_polivu_",
    "sensor.smart_irrigation_", "sensor.inverter_battery",
    "sensor.zariadka_", "binary_sensor.cam1_", "water_heater.",
    "climate.terneo_", "switch.avtopoliv_", "switch.mini_switch_k601_2_switch_1_2",
    "sensor.2_floor_", "weather.",
)
rows = []
for state in get("/api/states"):
    entity_id = state["entity_id"]
    if entity_id.startswith(KEEP_PREFIX):
        unit = state["attributes"].get("unit_of_measurement") or ""
        name = state["attributes"].get("friendly_name") or entity_id
        rows.append(f"{name} [{entity_id}] = {state['state']} {unit}".strip())
print("\n".join(sorted(rows)))
PY
)

if [ -z "$CONTEXT" ]; then
  echo "порожній контекст - HA не відповів" >>"$LOG"
  exit 1
fi

PROMPT="Ти аналітик розумного будинку. Нижче — лише поточний зріз стану систем на $(date '+%Y-%m-%d %H:%M'), а не історія за добу.

Дай стислий звіт українською, не більше 200 слів, у форматі:
1. Поточний стан — найважливіші активні навантаження та режими.
2. Аномалії — лише показники, які безпосередньо підтверджені зрізом.
3. Рекомендація — одна конкретна безпечна дія з найбільшим ефектом.

Тарифи: день 07:00–22:59 = 5.00 грн/кВт·год, ніч 23:00–06:59 = 2.50 грн.
Не роби висновків про джерело живлення, зміну за добу чи справність обладнання, якщо відповідних даних немає. Не вигадуй даних. Недоступні показники позначай як недоступні.

ПОТОЧНИЙ СТАН:
$CONTEXT"

RESULT=$(cd /home/forlinx/house-analyst && timeout 600 claude -p "$PROMPT" </dev/null 2>>"$LOG")
RC=$?

if [ "$RC" -ne 0 ] || [ -z "$RESULT" ]; then
  echo "claude завершився з кодом $RC" >>"$LOG"
  RESULT="Аналіз не вдався (код $RC). Перевір авторизацію командою: claude auth status."
fi

printf '%s' "$RESULT" >"$OUT_MD"
/userdata/hass/venv/bin/python - "$HA" "$TOKEN" "$OUT_MD" "$OUT_JSON" <<'PY'
import datetime
import json
import sys
import urllib.request

ha, tok, markdown_path, json_path = sys.argv[1:5]
with open(markdown_path, encoding="utf-8") as source:
    text = source.read()
with open(json_path, "w", encoding="utf-8") as destination:
    json.dump(
        {"generated": datetime.datetime.now().isoformat(timespec="seconds"), "text": text},
        destination,
        ensure_ascii=False,
        indent=2,
    )
body = json.dumps(
    {"title": "Аналіз будинку", "message": text, "notification_id": "house_analyst"}
).encode()
request = urllib.request.Request(
    ha + "/api/services/persistent_notification/create", data=body
)
request.add_header("Authorization", "Bearer " + tok)
request.add_header("Content-Type", "application/json")
urllib.request.urlopen(request, timeout=30).read()
PY

echo "=== $(date -Is) готово (rc=$RC, $(wc -c <"$OUT_MD") байт) ===" >>"$LOG"
