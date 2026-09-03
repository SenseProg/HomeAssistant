#!/usr/bin/env python3
"""Резервна копія довгострокової статистики на NAS.

Навіщо. 23.08.2026 зʼясувалося, що щоденні бекапи Home Assistant **не містять
бази взагалі**: у кожному `backup.json` від 11 до 23 серпня стоїть
`"exclude_database": true`. Ті 5-8 ГБ - це медіа й motion-кліпи. Тобто копії
статистики не існувало ніколи, і саме тому корупція бази 18 серпня забрала три
тижні історії безповоротно.

Копіювати всю базу немає сенсу: з 568 МБ на статистику припадає 18. Решта -
`states` і `state_attributes`, тобто сім діб докладної історії, яка й так
чиститься за розкладом і нічого не варта через тиждень. Береться те, що
незамінне:

    statistics             2,5 МБ   погодинні точки, безстроково
    statistics_short_term   15,5 МБ  пʼятихвилинні, поточний період
    statistics_meta          0,0 МБ  без неї попередні дві - купа чисел
    statistics_runs          0,1 МБ

`statistics_meta` тут не для повноти: у `statistics` лежить `metadata_id`, а не
назва сутності. Без цієї таблиці відновити ряд неможливо - будуть числа без
імен.

Знімок узгоджений. База відкривається лише на читання, і всі чотири таблиці
копіюються всередині однієї транзакції: у режимі WAL читач бачить базу такою,
якою вона була на момент її початку, навіть поки Home Assistant пише далі.
Зупиняти його не треба.

Знімок будується на ЛОКАЛЬНОМУ диску, і лише стиснений результат їде на NAS.
Перша версія писала SQLite прямо в NFS-теку і не вклалася у дві хвилини:
триста тисяч рядків окремими сторінками по мережі - це не те, для чого NFS. На
локальній карті ті самі таблиці копіюються за секунди, а на NAS іде один файл
на кілька мегабайтів.

    python backup_statistics.py            зробити копію і прибрати старі
    python backup_statistics.py --list     що вже лежить
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

DB = Path(os.environ.get("HA_RECORDER_DB", "/userdata/hass/config/home-assistant_v2.db"))


def _default_dest() -> str:
    # 03.09.2026: копії лежали в backups/statistics - тобто всередині дерева
    # конфігу, і 136 МБ .gz їхали в кожен нічний архів HA (backups/*.tar
    # виключено, backups/statistics/*.gz - ні). Після finish-video-move.sh
    # шара NAS змонтована поза деревом, і копії живуть у MB35x8/statistics
    # поруч із backups; до того - старий шлях, щоб 03:50 не писало на плату.
    new = Path("/mnt/homemate_media/video")
    if os.path.ismount(new):
        return str(new / "MB35x8" / "statistics")
    return "/userdata/hass/config-standalone/backups/statistics"


DEST = Path(os.environ.get("STATS_BACKUP_DIR") or _default_dest())
TABLES = ("statistics_meta", "statistics", "statistics_short_term", "statistics_runs")
KEEP = 30

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def make_snapshot(tmp: Path) -> dict[str, int]:
    """Копія чотирьох таблиць у новий файл, одним узгодженим читанням."""
    src = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=60)
    try:
        src.execute("begin")  # відкриває знімок; WAL дозволяє HA писати далі
        src.execute("attach database ? as dest", (str(tmp),))
        counts = {}
        for table in TABLES:
            src.execute("create table dest.%s as select * from main.%s" % (table, table))
            counts[table] = src.execute(
                "select count(*) from dest.%s" % table
            ).fetchone()[0]
        src.execute("commit")
        src.execute("detach database dest")
    finally:
        src.close()
    return counts


def depth(path: Path) -> dict[str, object]:
    conn = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        row = conn.execute("select min(start_ts), max(start_ts) from statistics").fetchone()
        series = conn.execute("select count(*) from statistics_meta").fetchone()[0]
    finally:
        conn.close()
    if not row or row[0] is None:
        return {"series": series, "days": 0}
    fmt = lambda t: time.strftime("%Y-%m-%d %H:%M", time.localtime(t))  # noqa: E731
    return {
        "series": series,
        "oldest": fmt(row[0]),
        "newest": fmt(row[1]),
        "days": round((row[1] - row[0]) / 86400, 1),
    }


def cmd_backup(args: argparse.Namespace) -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    scratch = Path(os.environ.get("STATS_SCRATCH", "/userdata/hass/config"))
    tmp = scratch / ("statistics-snapshot-%s.db" % stamp)
    if tmp.exists():
        tmp.unlink()

    try:
        counts = make_snapshot(tmp)
        info = depth(tmp)
        raw_size = tmp.stat().st_size
        final = DEST / ("statistics-%s.db.gz" % stamp)
        with open(tmp, "rb") as raw, gzip.open(final, "wb", compresslevel=6) as gz:
            shutil.copyfileobj(raw, gz)
    finally:
        # Обірваний запуск не має лишати по собі напівфабрикат: наступного разу
        # його прийняли б за копію.
        for leftover in (tmp, Path(str(tmp) + "-journal"), Path(str(tmp) + "-wal")):
            if leftover.exists():
                leftover.unlink()

    # Прибрати старі. Ретенція за кількістю, а не за датою: якщо плата
    # простоїть тиждень, останні копії мають лишитися, а не зникнути за віком.
    existing = sorted(DEST.glob("statistics-*.db.gz"))
    removed = 0
    for old in existing[:-args.keep] if len(existing) > args.keep else []:
        old.unlink()
        removed += 1

    print(
        json.dumps(
            {
                "file": final.name,
                "raw_bytes": raw_size,
                "gz_bytes": final.stat().st_size,
                "rows": counts,
                "coverage": info,
                "kept": min(len(existing), args.keep),
                "removed": removed,
            },
            ensure_ascii=False,
        )
    )


def cmd_list(args: argparse.Namespace) -> None:
    files = sorted(DEST.glob("statistics-*.db.gz"))
    print(
        json.dumps(
            {
                "dir": str(DEST),
                "count": len(files),
                "total_bytes": sum(f.stat().st_size for f in files),
                "files": [
                    {"name": f.name, "bytes": f.stat().st_size} for f in files[-10:]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", type=int, default=KEEP)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    (cmd_list if args.list else cmd_backup)(args)


if __name__ == "__main__":
    main()
