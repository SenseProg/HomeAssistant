#!/usr/bin/env python3
"""Похвилинний рівень зберігання з власною ретенцією.

Навіщо. Home Assistant має три рівні й жодного між ними: сира зміна стану
(живе `purge_keep_days`, зараз 7 діб), пʼятихвилинна `statistics_short_term`
(чиститься разом із recorder) і погодинна `statistics` (безстроково). Кроку
"хвилина за останні 30 днів" немає, і зробити його налаштуванням не можна:
`purge_keep_days` глобальний, не по сутностях.

Тому цей рівень живе збоку, у власній маленькій базі. Ціна мізерна: 1440
записів на добу на сенсор, тобто кілька мегабайтів за 30 днів, проти 73 МБ на
добу, які коштувало б секундне опитування у штатному `states`.

Сховище своє, а не таблиця recorder-бази, свідомо: у неї пише Home Assistant, і
чужий писар у ній - це те, чим 22.08.2026 уже поламали статистику. Окремий файл
не заважає нікому і переживає будь-яку операцію над основною базою.

Підкоманди:
    sample   --entities <id,...>   зняти поточні значення (раз на хвилину)
    export   [--entity <id>] [--hours N]   JSON для command_line-сенсора
    purge    [--days 30]           прибрати старе
    stats                          що всередині

Читає останні значення прямо з бази recorder, лише на читання - жодних токенів
і жодної залежності від того, що вже зламане.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

DB_PATH = Path(
    os.environ.get("MINUTE_ROLLUP_DB", "/userdata/hass/config/minute_rollup.db")
)
RECORDER_DB = Path(
    os.environ.get("HA_RECORDER_DB", "/userdata/hass/config/home-assistant_v2.db")
)
DEFAULT_RETENTION_DAYS = 30


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("pragma journal_mode=wal")
    conn.execute(
        "create table if not exists samples ("
        " entity_id text not null,"
        " ts integer not null,"
        " value real,"
        " primary key (entity_id, ts))"
    )
    return conn


def read_states(entity_ids: list[str]) -> dict[str, float | None]:
    """Останнє значення кожної сутності - прямо з бази recorder, лише на читання.

    Спершу тут був REST API, і це була помилка: він потребує токена у
    /home/forlinx/.ha_token, якого на платі немає з самого початку. Через цей
    самий токен уже не працюють energy-flow-health і house-analyst, а невдалі
    запити з ним одного разу забанили localhost. Рівень зберігання не має
    залежати від того, що зламане.

    База відкривається з mode=ro: писати в неї має право лише Home Assistant.
    """
    values: dict[str, float | None] = {}
    try:
        conn = sqlite3.connect(
            "file:" + str(RECORDER_DB) + "?mode=ro", uri=True, timeout=15
        )
    except sqlite3.Error:
        return {entity_id: None for entity_id in entity_ids}
    for entity_id in entity_ids:
        row = conn.execute(
            "select s.state from states s"
            " join states_meta m on m.metadata_id = s.metadata_id"
            " where m.entity_id = ? order by s.last_updated_ts desc limit 1",
            (entity_id,),
        ).fetchone()
        try:
            values[entity_id] = float(row[0]) if row else None
        except (TypeError, ValueError):
            # unavailable / unknown: пропуск у ряді чесніший за нуль, який
            # потім прочитають як реальне значення.
            values[entity_id] = None
    conn.close()
    return values


def cmd_sample(args: argparse.Namespace) -> None:
    entity_ids = [e.strip() for e in args.entities.split(",") if e.strip()]
    values = read_states(entity_ids)
    minute = int(time.time() // 60 * 60)
    conn = connect()
    written = 0
    for entity_id, value in values.items():
        if value is None:
            continue
        conn.execute(
            "insert or replace into samples (entity_id, ts, value) values (?,?,?)",
            (entity_id, minute, value),
        )
        written += 1
    conn.commit()
    conn.close()
    print(json.dumps({"written": written, "skipped": len(values) - written}))


def cmd_export(args: argparse.Namespace) -> None:
    conn = connect()
    since = int(time.time()) - args.hours * 3600
    if args.entity:
        rows = conn.execute(
            "select entity_id, ts, value from samples"
            " where entity_id=? and ts>=? order by ts",
            (args.entity, since),
        ).fetchall()
    else:
        rows = conn.execute(
            "select entity_id, ts, value from samples where ts>=? order by ts",
            (since,),
        ).fetchall()
    series: dict[str, list[list[float]]] = {}
    for entity_id, ts, value in rows:
        series.setdefault(entity_id, []).append([ts, value])
    conn.close()
    print(
        json.dumps(
            {"count": len(rows), "hours": args.hours, "series": series},
            ensure_ascii=False,
        )
    )


def cmd_purge(args: argparse.Namespace) -> None:
    conn = connect()
    cutoff = int(time.time()) - args.days * 86400
    removed = conn.execute("delete from samples where ts < ?", (cutoff,)).rowcount
    conn.commit()
    conn.execute("vacuum")
    conn.close()
    print(json.dumps({"removed": removed, "kept_days": args.days}))


def cmd_stats(_: argparse.Namespace) -> None:
    if not DB_PATH.is_file():
        print(json.dumps({"error": "no_db", "db": str(DB_PATH)}))
        return
    conn = connect()
    total = conn.execute("select count(*) from samples").fetchone()[0]
    bounds = conn.execute("select min(ts), max(ts) from samples").fetchone()
    per_entity = conn.execute(
        "select entity_id, count(*) from samples group by 1 order by 2 desc"
    ).fetchall()
    conn.close()
    print(
        json.dumps(
            {
                "db": str(DB_PATH),
                "size_bytes": DB_PATH.stat().st_size,
                "rows": total,
                "oldest": bounds[0],
                "newest": bounds[1],
                "days": round((bounds[1] - bounds[0]) / 86400, 2) if bounds[0] else 0,
                "entities": dict(per_entity),
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sample")
    p.add_argument("--entities", required=True)
    p.set_defaults(func=cmd_sample)

    p = sub.add_parser("export")
    p.add_argument("--entity")
    p.add_argument("--hours", type=int, default=24)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("purge")
    p.add_argument("--days", type=int, default=DEFAULT_RETENTION_DAYS)
    p.set_defaults(func=cmd_purge)

    p = sub.add_parser("stats")
    p.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
