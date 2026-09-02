#!/usr/bin/env python3
"""Хто відвалюється: епізоди і час недоступності ключових пристроїв за 7 днів.

Навіщо. Питання «додати стабільності кожному пристрою?» (02.09.2026) не має
сенсу без цифр: із 23 пристроїв справжніх «флаперів» виявилось чотири, а
решта недоступна менше 3 % часу, і то здебільшого через рестарти HA. Тому
таблиця живе на вкладці «Пристрої → Звʼязок» і перераховується сама.

Джерело - історія recorder через REST /api/history/period (лише стани, без
атрибутів). Епізод - перехід у unavailable/unknown із будь-якого іншого стану;
час - сума таких відрізків. Рестарт HA дає епізод усім пристроям одночасно,
тому 4-6 епізодів на тиждень при малому часі - це фон, а не проблема.

Вивід - JSON для command_line-сенсора: стан = кількість пристроїв, які були
недоступні понад 5 % часу; рядки - в атрибуті rows.
"""

from __future__ import annotations

import datetime
import json
import sys
import urllib.parse
import urllib.request

TOKEN_FILE = "/home/forlinx/.ha_token"
DAYS = 7
BAD = ("unavailable", "unknown")

# Назва, сутність. Одна опорна сутність на пристрій; новий пристрій - один рядок.
DEVICES = [
    ("Deye (логер .179)", "sensor.inverter_battery"),
    ("Насос свердловини T34 .26", "switch.t34_smart_plug_switch_1_2"),
    ("Мала пралка .82", "switch.mala_pralna_mashina_socket"),
    ("Контролер поливу .221", "switch.avtopoliv_kontroler_avtopoliv_klapan_1"),
    ("Насос поливу K601 .91", "switch.mini_switch_k601_2_switch_1_2"),
    ("Лічильник вводу .219", "sensor.energy_meter_phase_a_power_2"),
    ("Зарядка авто .36", "sensor.zariadka_7_5kvt_device_kw"),
    ("Бойлер бабусі", "switch.boiler_babusi_socket"),
    ("Сушарка", "switch.sushka_socket"),
    ("Terneo 1", "climate.terneo_1"),
    ("Terneo 2", "climate.terneo_2"),
    ("Бойлер Midea", "water_heater.144036023323246_water_heater"),
    ("Blauberg хлопці .27", "fan.siku_blauberg_fan_192_168_50_27"),
    ("Blauberg Олеся .123", "fan.siku_blauberg_fan_192_168_50_123"),
    ("PRANA .246", "fan.2_floor_supply_fan"),
    ("Камера .201", "binary_sensor.hikvision_camera_online"),
    ("NAS .25", "binary_sensor.cloudmate_nas_online"),
    ("Дім бабусі T&H (хмара)", "sensor.2i_poverkh_t_h_temperature"),
    ("Лічильник, хмарний показ", "sensor.energy_meter_total_energy"),
    ("Zigbee Гостьова", "sensor.sonoff_a48001c18f_temperature"),
    ("Zigbee Олеся", "sensor.kimnata_olesi_sonoff_a480144e06_temperature"),
    ("Пралка SmartThings", "sensor.pralnia_pralna_mashina_machine_state"),
]


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    try:
        token = open(TOKEN_FILE, encoding="utf-8").read().strip()
    except OSError:
        print(json.dumps({"error": "token_missing", "flaky": 0, "rows": []}))
        return 0
    now = datetime.datetime.now(datetime.timezone.utc)
    start = now - datetime.timedelta(days=DAYS)
    query = urllib.parse.urlencode(
        {
            "filter_entity_id": ",".join(e for _, e in DEVICES),
            "minimal_response": "1",
            "no_attributes": "1",
            "end_time": now.isoformat().replace("+00:00", "Z"),
        }
    )
    url = (
        "http://localhost:8123/api/history/period/"
        + start.isoformat().replace("+00:00", "Z")
        + "?"
        + query
    )
    try:
        request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
        data = json.load(urllib.request.urlopen(request, timeout=110))
    except Exception as exc:  # noqa: BLE001 - будь-яка біда має віддати JSON, не трейсбек
        print(json.dumps({"error": type(exc).__name__, "flaky": 0, "rows": []}))
        return 0
    history = {series[0]["entity_id"]: series for series in data if series}
    total = (now - start).total_seconds()
    rows = []
    for name, entity_id in DEVICES:
        series = history.get(entity_id)
        if not series:
            rows.append({"name": name, "entity": entity_id, "episodes": None, "hours": None, "pct": None, "state": "немає історії"})
            continue
        episodes = 0
        bad_seconds = 0.0
        prev_state = None
        prev_time = start
        for item in series:
            when = datetime.datetime.fromisoformat(item["last_changed"].replace("Z", "+00:00"))
            if prev_state in BAD:
                bad_seconds += (when - prev_time).total_seconds()
            if item["state"] in BAD and prev_state is not None and prev_state not in BAD:
                episodes += 1
            prev_state, prev_time = item["state"], when
        if prev_state in BAD:
            bad_seconds += (now - prev_time).total_seconds()
        rows.append(
            {
                "name": name,
                "entity": entity_id,
                "episodes": episodes,
                "hours": round(bad_seconds / 3600, 1),
                "pct": round(100 * bad_seconds / total, 1),
                "state": series[-1]["state"],
            }
        )
    rows.sort(key=lambda r: -(r["pct"] or 0))
    flaky = sum(1 for r in rows if (r["pct"] or 0) > 5)
    print(
        json.dumps(
            {
                "generated": now.astimezone().strftime("%Y-%m-%d %H:%M"),
                "days": DAYS,
                "flaky": flaky,
                "rows": rows,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
