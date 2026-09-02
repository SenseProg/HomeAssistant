#!/usr/bin/env python3
"""Історія ставок на електроенергію.

Ставка - часовий ряд, а не одне число. Доки ціни жили у двох помічниках
`input_number.tarif_den_07_00_22_59` та `input_number.tarif_nich_23_00_06_59`
і множилися в шаблонних сенсорах вартості, зміна ціни тихо переписувала
вартість усього минулого: вкладка «Витрати» показувала не скільки коштувало,
а скільки коштувало б за сьогоднішнім тарифом (docs/cost-history-recalc.md,
рядки 16-22). Таблиця з датою початку кожного періоду прибирає цю неправду:
момент часу однозначно вказує на період, а період - на ставку.

Сховище - JSON поруч із конфігурацією Home Assistant, як і журнал показників
води. Періоди тільки додаються, кінець періоду не зберігається зовсім: він
випливає з початку наступного, а два поля з тим самим змістом рано чи пізно
розійшлися б. Копій файлу скрипт не робить свідомо - таблиця росте
дописуванням, а не перезаписом, і лежить у git.

Команди:
    export                     JSON для command_line-сенсора
    rate --at <ISO>            яка ставка діяла в цей момент
    list                       усі періоди
    add --from <дата> (--flat R | --day R --night R) [--day-start] [--day-end]
        [--note] [--source] [--id]

Час скрізь київський: вікна день/ніч задані місцевим часом, а перехід на
літній час зсуває їх разом із годинником. Момент із власним зсувом (`+03:00`,
`Z`) переводиться в київський, момент без зсуву вважається вже київським.

Запис атомарний: тимчасовий файл + os.replace.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

KYIV = ZoneInfo("Europe/Kyiv")
BOARD_STORE = "/userdata/hass/config/tariffs.json"
VERSION = 1
DAY_MINUTES = 24 * 60


def store_path() -> str:
    """Шлях до таблиці.

    На платі файл лежить поруч із configuration.yaml, у репозиторії - поруч зі
    скриптом (board-config/tariffs.json). Один зашитий шлях не підходить обом,
    а скрипт має однаково запускатися і там, і там - інакше тести читали б не
    те, що працює на платі.
    """
    override = os.environ.get("TARIFFS_STORE")
    if override:
        return override
    if os.path.isfile(BOARD_STORE):
        return BOARD_STORE
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, os.pardir, "tariffs.json"))


def now_iso() -> str:
    return datetime.now(KYIV).isoformat(timespec="seconds")


def parse_hhmm(text: str) -> int:
    """«07:00» -> 420. «24:00» дозволено як кінець доби."""
    hours, _, minutes = str(text).partition(":")
    total = int(hours) * 60 + int(minutes or 0)
    if not 0 <= total <= DAY_MINUTES:
        raise ValueError(f"час поза добою: {text!r}")
    return total


def parse_instant(text: str) -> datetime:
    """ISO-рядок -> момент у київському часі.

    Рядок без зсуву означає київський час: людина, яка питає «яка ставка була
    3 серпня о 12:00», має на увазі свій годинник, а не UTC.
    """
    raw = str(text).strip().replace(" ", "T")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    moment = datetime.fromisoformat(raw)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=KYIV)
    return moment.astimezone(KYIV)


def period_start(period: dict) -> datetime | None:
    """Початок дії періоду. None - «діяв від початку спостережень»."""
    value = period.get("from")
    if value in (None, ""):
        return None
    return parse_instant(value)


def zone_ranges(zone: dict) -> list[tuple[int, int]]:
    """Вікно зони у хвилинах від опівночі, розрізане на непересічні відрізки."""
    start = parse_hhmm(zone["start"])
    end = parse_hhmm(zone["end"])
    if start == end:
        return [(0, DAY_MINUTES)]
    if start < end:
        return [(start, end)]
    # Вікно через північ - ніч 23:00-07:00 саме таке.
    return [(start, DAY_MINUTES), (0, end)]


def validate(data: dict) -> dict:
    """Перевірити таблицю перед використанням.

    Дірка чи накладка у вікнах не падає сама по собі - вона тихо віддає не ту
    ставку або жодної, і помилку видно лише через місяць у сумі за період.
    Тому таблиця перевіряється при кожному читанні, а не лише при записі.
    """
    periods = data.get("periods")
    if not isinstance(periods, list) or not periods:
        raise ValueError("у таблиці немає жодного періоду")
    seen_ids: set[str] = set()
    seen_starts: set[str] = set()
    for period in periods:
        pid = period.get("id")
        if not pid:
            raise ValueError("період без id")
        if pid in seen_ids:
            raise ValueError(f"дубль id періоду: {pid}")
        seen_ids.add(pid)
        key = str(period.get("from"))
        if key in seen_starts:
            raise ValueError(f"два періоди починаються однаково: {key}")
        seen_starts.add(key)
        zones = period.get("zones")
        if not isinstance(zones, list) or not zones:
            raise ValueError(f"період {pid} без зон")
        covered: list[tuple[int, int]] = []
        seen_zones: set[str] = set()
        for zone in zones:
            name = zone.get("name")
            if not name:
                raise ValueError(f"зона періоду {pid} без назви")
            # Назва зони - ключ у словнику `rates`, який їде атрибутом сенсора.
            # Дубль назви не падає сам: словник лишає лише останню ставку, і
            # картка мовчки показує нічну ціну замість денної. Таблиця росте
            # ручним дописуванням у git, тому саме тут дубль і зʼявиться.
            if name in seen_zones:
                raise ValueError(f"дубль назви зони {name} у періоді {pid}")
            seen_zones.add(name)
            if "start" not in zone or "end" not in zone:
                raise ValueError(f"зона {name} періоду {pid} без межі start/end")
            rate = zone.get("rate")
            # Ставка-рядок пройшла б далі й порахувалася б як текст: множення в
            # шаблоні дало б помилку не тут, а через добу в сумі за період.
            if isinstance(rate, bool) or not isinstance(rate, (int, float)):
                raise ValueError(f"ставка зони {name} періоду {pid} не число: {rate!r}")
            covered.extend(zone_ranges(zone))
        covered.sort()
        cursor = 0
        for start, end in covered:
            if start != cursor:
                raise ValueError(
                    f"вікна періоду {pid} не сходяться на {start // 60:02d}:{start % 60:02d}"
                )
            cursor = end
        if cursor != DAY_MINUTES:
            raise ValueError(f"вікна періоду {pid} не покривають добу")
    return data


def sort_periods(periods: list[dict]) -> list[dict]:
    """Найраніший спершу; період без дати початку - завжди перший."""
    return sorted(
        periods,
        key=lambda period: (
            period_start(period) is not None,
            period_start(period) or datetime.min.replace(tzinfo=KYIV),
        ),
    )


def load(required: bool = True) -> dict:
    path = store_path()
    if not os.path.isfile(path):
        if required:
            # Таблиця - частина конфігурації, а не наростаючий журнал. Порожній
            # каркас замість неї означав би нульову ставку і мовчки нульову
            # вартість, тому читання без файлу має падати вголос.
            raise ValueError(f"таблиця тарифів не знайдена: {path}")
        return {
            "version": VERSION,
            "currency": "UAH",
            "unit": "kWh",
            "timezone": "Europe/Kyiv",
            "updated_at": None,
            "note": "",
            "periods": [],
        }
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    data.setdefault("version", VERSION)
    data.setdefault("currency", "UAH")
    data.setdefault("unit", "kWh")
    data.setdefault("timezone", "Europe/Kyiv")
    data.setdefault("periods", [])
    data["periods"] = sort_periods(data["periods"])
    if required:
        validate(data)
    return data


def save(data: dict) -> None:
    data["version"] = VERSION
    data["updated_at"] = now_iso()
    data["periods"] = sort_periods(data["periods"])
    validate(data)
    path = store_path()
    temp = f"{path}.tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def period_at(data: dict, moment: datetime) -> tuple[dict, bool]:
    """Період, чинний на момент. Другим значенням - чи момент раніший за таблицю.

    Майбутня дата свідомо бере останній період: інакше сенсор ставав би
    недоступним щоразу, коли хтось питає про завтра.
    """
    periods = sort_periods(data["periods"])
    chosen = None
    for period in periods:
        start = period_start(period)
        if start is None or start <= moment:
            chosen = period
    if chosen is None:
        # Усі відомі періоди починаються пізніше. Найраніша відома ставка з
        # чесною позначкою корисніша за відмову відповідати.
        return periods[0], True
    return chosen, False


def zone_at(period: dict, moment: datetime) -> dict:
    local = moment.astimezone(KYIV)
    minutes = local.hour * 60 + local.minute
    for zone in period["zones"]:
        for start, end in zone_ranges(zone):
            if start <= minutes < end:
                return zone
    raise ValueError(f"період {period['id']} не має вікна на {local:%H:%M}")


def kind(period: dict) -> str:
    """Вид тарифу виводиться зі складу зон, а не зберігається окремим полем."""
    return "flat" if len(period["zones"]) == 1 else "zoned"


def row(period: dict, nxt: dict | None, active: bool) -> dict:
    return {
        "id": period["id"],
        "from": period.get("from"),
        "until": (nxt or {}).get("from"),
        "kind": kind(period),
        "active": active,
        "rates": {zone["name"]: zone["rate"] for zone in period["zones"]},
        "zones": [
            {
                "name": zone["name"],
                "label": zone.get("label", zone["name"]),
                "rate": zone["rate"],
                "window": f"{zone['start']}-{zone['end']}",
            }
            for zone in period["zones"]
        ],
        "note": period.get("note", ""),
        "source": period.get("source", ""),
    }


def rows(data: dict, active_id: str | None) -> list[dict]:
    periods = sort_periods(data["periods"])
    return [
        row(period, periods[index + 1] if index + 1 < len(periods) else None, period["id"] == active_id)
        for index, period in enumerate(periods)
    ]


def cmd_export(args: argparse.Namespace) -> dict:
    """Компактний зріз для command_line-сенсора.

    Стан сенсора - лише чинна ставка (`value_json.rate_now`); межа стану в 255
    символів не дозволяє класти туди таблицю, тому періоди їдуть атрибутами.
    """
    data = load()
    moment = parse_instant(args.at) if args.at else datetime.now(KYIV)
    period, before_first = period_at(data, moment)
    zone = zone_at(period, moment)
    return {
        "rate_now": zone["rate"],
        "zone_now": zone["name"],
        "zone_label": zone.get("label", zone["name"]),
        "rates": {item["name"]: item["rate"] for item in period["zones"]},
        "periods_count": len(data["periods"]),
        "current_id": period["id"],
        "current_from": period.get("from"),
        "current_kind": kind(period),
        "before_first_period": before_first,
        "currency": data.get("currency", "UAH"),
        "unit": data.get("unit", "kWh"),
        "updated_at": data.get("updated_at"),
        "periods": rows(data, period["id"]),
    }


def cmd_rate(args: argparse.Namespace) -> dict:
    data = load()
    moment = parse_instant(args.at)
    period, before_first = period_at(data, moment)
    zone = zone_at(period, moment)
    return {
        "at": args.at,
        "kyiv": moment.isoformat(timespec="seconds"),
        "rate": zone["rate"],
        "zone": zone["name"],
        "zone_label": zone.get("label", zone["name"]),
        "window": f"{zone['start']}-{zone['end']}",
        "period": period["id"],
        "period_from": period.get("from"),
        "before_first_period": before_first,
        "currency": data.get("currency", "UAH"),
        "unit": data.get("unit", "kWh"),
    }


def cmd_list(args: argparse.Namespace) -> dict:
    data = load()
    period, _ = period_at(data, datetime.now(KYIV))
    return {
        "count": len(data["periods"]),
        "currency": data.get("currency", "UAH"),
        "unit": data.get("unit", "kWh"),
        "updated_at": data.get("updated_at"),
        "periods": rows(data, period["id"]),
    }


def make_id(args: argparse.Namespace) -> str:
    stamp = "".join(char for char in str(args.start) if char.isdigit())[:8]
    return f"flat-{stamp}" if args.flat is not None else f"day-night-{stamp}"


def cmd_add(args: argparse.Namespace) -> dict:
    """Додати період. Нова ціна не чіпає жодного попереднього періоду."""
    if args.flat is not None and (args.day is not None or args.night is not None):
        raise ValueError("--flat не поєднується з --day/--night")
    if args.flat is None and (args.day is None or args.night is None):
        raise ValueError("потрібно або --flat, або пара --day і --night")
    start = parse_instant(args.start)
    if args.flat is not None:
        zones = [
            {
                "name": "doba",
                "label": "Цілодобово",
                "rate": round(float(args.flat), 4),
                "start": "00:00",
                "end": "00:00",
            }
        ]
    else:
        zones = [
            {
                "name": "den",
                "label": "День",
                "rate": round(float(args.day), 4),
                "start": args.day_start,
                "end": args.day_end,
            },
            {
                "name": "nich",
                "label": "Ніч",
                "rate": round(float(args.night), 4),
                "start": args.day_end,
                "end": args.day_start,
            },
        ]
    # Файл може ще не існувати лише при першому розгортанні, тому саме тут
    # читання не вимагає його наявності.
    data = load(required=False)
    period = {
        "id": args.id or make_id(args),
        "from": args.start,
        "zones": zones,
        "source": args.source or "",
        "note": args.note or "",
    }
    if any(existing["id"] == period["id"] for existing in data["periods"]):
        raise ValueError(f"період {period['id']} уже є")
    if any(period_start(existing) == start for existing in data["periods"]):
        raise ValueError(f"період із початком {args.start} уже є")
    data["periods"].append(period)
    save(data)
    return {"ok": True, "action": "add", "id": period["id"], "from": period["from"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="JSON для command_line-сенсора")
    export.add_argument("--at", default="")
    export.set_defaults(func=cmd_export)

    rate = sub.add_parser("rate", help="ставка на момент часу")
    rate.add_argument("--at", required=True)
    rate.set_defaults(func=cmd_rate)

    listing = sub.add_parser("list", help="усі періоди")
    listing.set_defaults(func=cmd_list)

    add = sub.add_parser("add", help="додати період")
    add.add_argument("--from", dest="start", required=True)
    add.add_argument("--flat", default=None)
    add.add_argument("--day", default=None)
    add.add_argument("--night", default=None)
    add.add_argument("--day-start", default="07:00")
    add.add_argument("--day-end", default="23:00")
    add.add_argument("--note", default="")
    add.add_argument("--source", default="")
    add.add_argument("--id", default="")
    add.set_defaults(func=cmd_add)

    args = parser.parse_args()
    try:
        result = args.func(args)
    except SystemExit:
        raise
    except Exception as error:  # noqa: BLE001 - сервіс має віддати причину, а не трейс
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
