#!/usr/bin/env python3
"""Журнал сповіщень у власній базі.

Навіщо. Сповіщення в Home Assistant не зберігаються ніде. `notify.mobile_app_*`
віддає повідомлення застосунку на телефоні й забуває його тієї ж миті, а
`persistent_notification` живе **тільки в оперативній памʼяті** - це не таблиця,
і після кожного рестарту панель порожня. 23.08.2026 у конфігурації було 33
виклики push проти 22 записів у панель: одинадцять тривог не лишали в системі
жодного сліду взагалі.

Наслідок не косметичний. Сторож, який спрацював о третій ночі, поки ви спали, і
зник під час ранкового рестарту, - це сторож, якого не було.

Тому журнал живе збоку, у власному файлі, як і похвилинні зрізи. Розмір
мізерний: сповіщення - це рядок тексту, а не телеметрія. Тисяча записів важить
менше за одну хвилину показників трьох сенсорів.

Записи не чистяться за віком. Ретенція тут була б помилкою: цінність тривоги
зростає з часом, бо саме старі записи відповідають на питання "коли це почалося"
і "чи було таке раніше". `purge` є, але вручну і за явним числом днів.

Лічильник показує НЕПРОЧИТАНІ, а не всі за добу. Позначка одна на весь журнал -
мітка часу останнього прочитання; усе, що старіше, вважається прочитаним. Це та
сама модель, що в поштовій скриньці, і вона не потребує ані окремого стану на
кожен запис, ані звірки з тим, що людина справді відкрила.

Підкоманди:
    log --title T --message M [--service S] [--level L] [--key K]
    export [--limit N] [--since-days D]     JSON для command_line-сенсора
    mark-read [--ts N] | mark-read --key K  усе донині / лише один запис
    stats                                   що всередині
    purge --days N                          прибрати старіше за N діб
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
    os.environ.get("NOTIFY_LOG_DB", "/userdata/hass/config/notifications.db")
)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("pragma journal_mode=wal")
    conn.execute(
        "create table if not exists notifications ("
        " id integer primary key autoincrement,"
        " ts integer not null,"
        " service text,"
        " level text,"
        " title text,"
        " message text)"
    )
    conn.execute("create index if not exists ix_notifications_ts on notifications(ts)")
    conn.execute("create table if not exists meta (key text primary key, value text)")
    # 02.09.2026: ключ запису і прапорець «прочитано» на кожен рядок. Ключ - md5
    # від заголовка і тексту, той самий, що стоїть у notification_id панелі HA
    # (nl_<key>): закриття сповіщення в панелі позначає прочитаним саме цей
    # запис, а не весь журнал. Мітка last_read_ts лишається для кнопки «усе».
    cols = {row[1] for row in conn.execute("pragma table_info(notifications)")}
    if "key" not in cols:
        conn.execute("alter table notifications add column key text")
    if "read" not in cols:
        conn.execute("alter table notifications add column read integer not null default 0")
    return conn


def last_read(conn: sqlite3.Connection) -> int:
    row = conn.execute("select value from meta where key='last_read_ts'").fetchone()
    try:
        return int(row[0]) if row else 0
    except (TypeError, ValueError):
        return 0


def cmd_log(args: argparse.Namespace) -> None:
    conn = connect()
    conn.execute(
        "insert into notifications (ts, service, level, title, message, key) values (?,?,?,?,?,?)",
        (int(time.time()), args.service, args.level, args.title, args.message, args.key or None),
    )
    conn.commit()
    total = conn.execute("select count(*) from notifications").fetchone()[0]
    conn.close()
    print(json.dumps({"logged": True, "total": total}, ensure_ascii=False))


def cmd_export(args: argparse.Namespace) -> None:
    """JSON для command_line-сенсора.

    Стан сенсора - кількість за добу, а не текст: у стану Home Assistant ліміт
    255 символів, і довге повідомлення зробило б сутність недоступною. Самі
    записи їдуть в атрибути, де ліміту немає.
    """
    if not DB_PATH.is_file():
        print(json.dumps({"unread": 0, "today": 0, "total": 0, "items": []}))
        return
    conn = connect()
    since = int(time.time()) - args.since_days * 86400
    rows = conn.execute(
        "select ts, service, level, title, message, key, read from notifications"
        " where ts >= ? order by ts desc limit ?",
        (since, args.limit),
    ).fetchall()
    marker = last_read(conn)
    # Одна подія - один запис. script.spovistyty_vsikh шле той самий текст на
    # три телефони, і журнал діставав три однакові рядки поспіль: 73 рядки за
    # 2 вересня 2026 були ~20 подіями. Тут сусідні рядки з тим самим заголовком
    # і текстом у межах 20 секунд згортаються в один із лічильником kopii.
    # У базі лишаються всі рядки - згортання лише для показу.
    merged: list[dict] = []
    for r in rows:
        if (
            merged
            and merged[-1]["_t"] == r[3]
            and merged[-1]["_m"] == (r[4] or "")
            and merged[-1]["_ts"] - r[0] <= 20
        ):
            merged[-1]["kopii"] += 1
            continue
        merged.append({"_ts": r[0], "_t": r[3], "_m": r[4] or "", "row": r, "kopii": 1})
    unread = conn.execute(
        "select count(*) from notifications where ts > ? and read = 0", (marker,)
    ).fetchone()[0]
    day_ago = int(time.time()) - 86400
    today = conn.execute(
        "select count(*) from notifications where ts >= ?", (day_ago,)
    ).fetchone()[0]
    total = conn.execute("select count(*) from notifications").fetchone()[0]
    conn.close()
    print(
        json.dumps(
            {
                "unread": unread,
                "today": today,
                "total": total,
                "last_read": (
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(marker))
                    if marker
                    else "ніколи"
                ),
                "items": [
                    {
                        "chas": time.strftime("%Y-%m-%d %H:%M", time.localtime(m["row"][0])),
                        "nove": m["row"][0] > marker and not m["row"][6],
                        "key": m["row"][5],
                        "service": m["row"][1],
                        "level": m["row"][2],
                        "title": m["row"][3],
                        "message": (m["row"][4] or "")[:300],
                        "kopii": m["kopii"],
                    }
                    for m in merged
                ],
            },
            ensure_ascii=False,
        )
    )


def cmd_mark_read(args: argparse.Namespace) -> None:
    """Позначити прочитаним усе до вказаної миті (типово - до зараз),
    або лише записи з ключем --key (закриття одного сповіщення в панелі HA)."""
    conn = connect()
    if args.key:
        n = conn.execute(
            "update notifications set read = 1 where key = ?", (args.key,)
        ).rowcount
        conn.commit()
        conn.close()
        print(json.dumps({"marked_key": args.key, "rows": n}))
        return
    ts = args.ts if args.ts is not None else int(time.time())
    conn.execute(
        "insert into meta (key, value) values ('last_read_ts', ?)"
        " on conflict(key) do update set value=excluded.value",
        (str(ts),),
    )
    conn.commit()
    unread = conn.execute(
        "select count(*) from notifications where ts > ?", (ts,)
    ).fetchone()[0]
    conn.close()
    print(json.dumps({"marked_until": ts, "unread": unread}))


def cmd_stats(_: argparse.Namespace) -> None:
    if not DB_PATH.is_file():
        print(json.dumps({"error": "no_db", "db": str(DB_PATH)}))
        return
    conn = connect()
    total = conn.execute("select count(*) from notifications").fetchone()[0]
    bounds = conn.execute("select min(ts), max(ts) from notifications").fetchone()
    by_title = conn.execute(
        "select title, count(*) c from notifications group by 1 order by c desc limit 10"
    ).fetchall()
    conn.close()
    fmt = lambda t: time.strftime("%Y-%m-%d %H:%M", time.localtime(t)) if t else None
    print(
        json.dumps(
            {
                "db": str(DB_PATH),
                "size_bytes": DB_PATH.stat().st_size,
                "total": total,
                "oldest": fmt(bounds[0]),
                "newest": fmt(bounds[1]),
                "top": [{"title": t, "count": c} for t, c in by_title],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_purge(args: argparse.Namespace) -> None:
    conn = connect()
    cutoff = int(time.time()) - args.days * 86400
    removed = conn.execute("delete from notifications where ts < ?", (cutoff,)).rowcount
    conn.commit()
    conn.execute("vacuum")
    conn.close()
    print(json.dumps({"removed": removed, "kept_days": args.days}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("log")
    p.add_argument("--key", default="", help="md5 заголовка і тексту, як у notification_id панелі")
    p.add_argument("--title", default="")
    p.add_argument("--message", default="")
    p.add_argument("--service", default="")
    p.add_argument("--level", default="info")
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("export")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--since-days", type=int, default=30, dest="since_days")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("mark-read")
    p.add_argument("--ts", type=int)
    p.add_argument("--key", default="", help="позначити прочитаними лише записи з цим ключем")
    p.set_defaults(func=cmd_mark_read)

    p = sub.add_parser("stats")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("purge")
    p.add_argument("--days", type=int, required=True)
    p.set_defaults(func=cmd_purge)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
