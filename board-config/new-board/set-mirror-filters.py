# -*- coding: utf-8 -*-
"""Заборонити копії керувати найнебезпечнішим у домі.

Дзеркальні сутності remote_homeassistant двосторонні: натискання на копії
виконує дію в домі. Для стенда це неприйнятно там, де ціна помилки висока -
термостат санвузла вмикати не можна взагалі, а випадково відкритий клапан
поливу коштує затоплення.

Виключене сюди не потрапляє зовсім: ні кнопкою, ні станом. Решта дому
дзеркалиться повністю, щоб копію можна було випробувати як справжню.

Домен script виключено цілком: усі десять скриптів у цьому домі - керування
поливом (poliv_zona_1..8, poliv_stop_all), і кожен з них запускає воду.
"""
import io, json, sys

P = "/userdata/hass/config/.storage/core.config_entries"

TERNEO = ["button.terneo_1_restart", "climate.terneo_1",
          "number.terneo_1_display_brightness", "number.terneo_1_hysteresis",
          "number.terneo_1_max_floor_temperature", "number.terneo_1_min_floor_temperature",
          "select.terneo_1_control_type", "select.terneo_1_sensor_type",
          "switch.terneo_1_children_lock", "switch.terneo_1_cooling_mode",
          "switch.terneo_1_night_brightness", "switch.terneo_1_power"]

POLIV = (["switch.avtopoliv_kontroler_avtopoliv_klapan_%d" % i for i in range(1, 9)] +
         ["switch.avtopoliv_kontroler_switch_%d" % i for i in range(1, 9)] +
         ["switch.mini_switch_k601_2_switch_1", "switch.mini_switch_k601_2_switch_1_2",
          "switch.mini_switch_k601_switch_1", "number.mini_switch_k601_2_switch_1_timer"])

store = json.load(io.open(P, encoding="utf-8"))
found = 0
for e in store["data"]["entries"]:
    if e["domain"] != "remote_homeassistant":
        continue
    if (e.get("data") or {}).get("host") is None:
        continue                      # це запис "remote node", у нього фільтрів немає
    opts = dict(e.get("options") or {})
    opts["exclude_entities"] = TERNEO + POLIV
    opts["exclude_domains"] = ["script"]
    e["options"] = opts
    found += 1
    print("  фільтри записано у:", e.get("title"))
    print("  виключено сутностей:", len(opts["exclude_entities"]))
    print("  виключено доменів:  ", opts["exclude_domains"])

if not found:
    print("ПОМИЛКА: запис зʼєднання не знайдено")
    sys.exit(1)

io.open(P, "w", encoding="utf-8").write(json.dumps(store, ensure_ascii=False, indent=2))
print("  збережено")
