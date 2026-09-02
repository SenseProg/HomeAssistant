#!/usr/bin/env python3
"""Сторож глибини довгострокової статистики Home Assistant.

18 серпня 2026 пошкодження бази recorder знищило всю статистику, накопичену
до цієї дати, і ніхто цього не помітив: за глибиною історії у проєкті не
стежив жоден сенсор. Наслідок видно на вкладці «Витрати» - картки «Цей
місяць» і «Цей рік» показують однакове число, бо в таблиці `statistics`
лишилося п'ять днів. Цей скрипт робить глибину вимірюваною величиною, щоб
наступне обнулення історії стало помітним того ж дня.

Друкує один рядок JSON: стан для сенсора - `depth_days`, решта полів іде в
атрибути. Глибина рахується як кількість РІЗНИХ місцевих календарних днів,
у яких є хоч один запис, а не як різниця дат: після часткової втрати
середини діапазону різниця дат бреше, а лічильник днів - ні. Провали
всередині діапазону окремо перелічені у `missing_days` (перші MISSING_LIMIT
штук; скільки їх усього - у `missing_days_total`).

Безпека:
  * база відкривається ЛИШЕ на читання - `file:...?mode=ro` плюс
    `PRAGMA query_only`. Це жива база працюючого HA, і жодна діагностика не
    має права її торкнутися;
  * будь-яка помилка (немає файла, база заблокована, немає таблиці) віддає
    JSON з полем `error` і кодом виходу 0. Ненульовий код HA трактує як
    збій команди й відкидає вивід разом із причиною - тобто сторож замовк
    би саме тоді, коли має кричати. Для скриптів у shell є `--strict`.

Приклад:
    lts_depth.py --db /userdata/hass/config/home-assistant_v2.db
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_DB = os.environ.get("LTS_DB", "/userdata/hass/config/home-assistant_v2.db")
# Порожній рядок означає «системна локаль плати». На платі це Europe/Kyiv
# (/etc/timezone), той самий пояс, що й `time_zone` у configuration.yaml, тож
# межі доби збігаються з тим, що людина бачить у картках.
DEFAULT_TZ = os.environ.get("LTS_TZ", "")
# Recorder тримає базу відкритою постійно. Чекати на неї довше кількох секунд
# немає сенсу: сенсор оновиться наступного разу, а зависла команда підвісила б
# і сам Home Assistant, бо command_line виконується в його циклі.
#
# Це бюджет на ВЕСЬ вимір, а не на окремий запит. sqlite відлічує busy_timeout
# заново для кожного запиту, а запитів тут чотири, тож самого лише timeout= у
# connect() було замало: на реально заблокованій базі (BEGIN EXCLUSIVE із
# сусіднього процесу) вимір тривав 7.34 с, а в найгіршому разі дав би 20 с.
# Home Assistant убиває command_line на 15-й секунді (DEFAULT_TIMEOUT = 15 у
# homeassistant/components/command_line/const.py) і разом із процесом викидає
# його вивід - сторож замовк би саме на заблокованій базі, тобто тоді, коли
# має кричати.
#
# Чому саме три секунди, а не п'ять: busy_timeout не є точною межею. Заміряно,
# що очікування перевищує задане десь у півтора раза (4000 мс -> 5.97 с,
# 30000 мс -> 42.1 с), а conn.interrupt() busy-очікування не перериває взагалі.
# Перший заблокований запит з'їдає весь бюджет, решта після цього падають за
# 0.03 с, тож увесь вимір укладається приблизно в 4.5 с - із запасом до тих 15.
# Втратити один зріз не страшно: сенсор опитується за розкладом і наступного
# разу дістане число. До того ж база живе в режимі WAL (перевірено на платі:
# `pragma journal_mode` -> wal), де читач із писарем взагалі не змагається.
READ_BUDGET = 3.0

# Скільки провалів перелічувати поіменно. Recorder відкидає ВСІ атрибути стану,
# щойно їхній JSON переростає MAX_STATE_ATTRS_BYTES = 16384 байти, і пише в
# базу порожній словник (homeassistant/components/recorder/db_schema.py). Одна
# дата коштує близько 14 байт, тож єдиний зіпсований start_ts (скажімо, 1970
# рік) роздув би список на тисячі рядків і стер би з історії заразом oldest,
# newest і error - усе, заради чого сторож і писався. Повна кількість провалів
# лишається в missing_days_total.
MISSING_LIMIT = 60

# Історичні розкладки колонки часу: сучасні версії HA пишуть unix-час у
# `start_ts`, старіші - текстову дату в `start`. Бекапи з NAS можуть бути
# і того, і того віку, тому підтримуємо обидві.
TIME_COLUMNS = ("start_ts", "start")


def _ro_uri(db_path: str) -> str:
    """URI лише для читання. Через Path.as_uri, щоб пробіли й кирилиця в шляху
    не ламали розбір URI, а Windows-шлях лишався валідним для sqlite."""
    return Path(db_path).resolve().as_uri() + "?mode=ro"


def _zone(name: str):
    """Пояс за іменем IANA. Порожнє ім'я - системна локаль (tz=None)."""
    if not name:
        return None
    from zoneinfo import ZoneInfo  # помилка тут - помилка конфігурації, хай кричить

    return ZoneInfo(name)


def _local(stamp: float, zone) -> datetime:
    return datetime.fromtimestamp(stamp, timezone.utc).astimezone(zone)


def _to_epoch(value) -> float | None:
    """Значення колонки часу -> unix-час. Текстова дата без пояса - UTC,
    бо recorder завжди зберігав статистику саме в UTC."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(" ", "T")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def _blank(db_path: str) -> dict:
    """Однаковий набір ключів у будь-якому результаті.

    Шаблон сенсора звертається до атрибутів напряму; якби при помилці частина
    ключів зникала, картка падала б з UndefinedError замість того, щоб показати
    причину.
    """
    return {
        "ok": False,
        "error": None,
        "detail": None,
        "db": db_path,
        "depth_days": None,
        "rows": None,
        "metadata": None,
        "hours": None,
        "oldest": None,
        "newest": None,
        "oldest_date": None,
        "newest_date": None,
        "span_days": None,
        "lag_days": None,
        "missing_days": [],
        "missing_days_total": 0,
        "measured_at": None,
    }


def _classify(error: Exception) -> str:
    text = str(error).lower()
    if "no such table" in text:
        return "no_statistics_table"
    if "locked" in text or "busy" in text:
        return "db_locked"
    if "malformed" in text or "not a database" in text or "encrypted" in text:
        return "db_corrupt"
    if "unable to open" in text:
        # Типовий випадок - база в режимі WAL без -shm: HA впав і не зробив
        # checkpoint. Читання без права створити -shm неможливе.
        return "db_unreadable"
    return "db_read_failed"


def _ask(conn: sqlite3.Connection, deadline: float, sql: str):
    """Запит із рештою спільного бюджету очікування.

    busy_timeout доводиться виставляти перед кожним запитом, бо sqlite відлічує
    його від нуля щоразу. Коли бюджет вичерпано, наступний запит на заблокованій
    базі падає негайно - і сторож устигає надрукувати JSON з причиною замість
    того, щоб бути вбитим за таймаутом разом із цією причиною.
    """
    left_ms = max(0, int((deadline - time.monotonic()) * 1000))
    conn.execute("PRAGMA busy_timeout = {0}".format(left_ms))
    return conn.execute(sql)


def _stamps(conn: sqlite3.Connection, deadline: float, column: str) -> list[float]:
    """Різні позначки часу. Statistics - погодинна таблиця, тож значень тут
    стільки, скільки годин історії. Вибірка йде по індексу
    `ix_statistics_start_ts`, тому коштує мілісекунди навіть на базі в пів
    гігабайта: виміряно на платі - 99 значень із 21902 рядків за 0.003 с."""
    rows = _ask(
        conn,
        deadline,
        "SELECT DISTINCT {0} FROM statistics WHERE {0} IS NOT NULL".format(column),
    )
    stamps = []
    for (value,) in rows:
        stamp = _to_epoch(value)
        if stamp is not None:
            stamps.append(stamp)
    return stamps


def read_depth(db_path: str = DEFAULT_DB, zone=None) -> dict:
    result = _blank(db_path)
    result["measured_at"] = datetime.now(timezone.utc).astimezone(zone).isoformat(
        timespec="seconds"
    )
    if not os.path.isfile(db_path):
        result["error"] = "db_missing"
        return result

    deadline = time.monotonic() + READ_BUDGET
    try:
        conn = sqlite3.connect(_ro_uri(db_path), uri=True, timeout=READ_BUDGET)
    except sqlite3.Error as error:
        result["error"] = _classify(error)
        result["detail"] = str(error)
        return result

    try:
        # Другий замок після mode=ro: навіть помилковий INSERT у майбутній
        # правці цього файла не дійде до диска.
        conn.execute("PRAGMA query_only = 1")
        columns = {
            row[1] for row in _ask(conn, deadline, "PRAGMA table_info(statistics)")
        }
        if not columns:
            result["error"] = "no_statistics_table"
            return result
        available = [name for name in TIME_COLUMNS if name in columns]
        if not available:
            result["error"] = "no_time_column"
            result["detail"] = "у таблиці statistics немає ані start_ts, ані start"
            return result

        result["rows"] = _ask(
            conn, deadline, "SELECT count(*) FROM statistics"
        ).fetchone()[0]
        try:
            result["metadata"] = _ask(
                conn, deadline, "SELECT count(*) FROM statistics_meta"
            ).fetchone()[0]
        except sqlite3.DatabaseError:
            # Метадані - довідник імен сенсорів. Його відсутність не заважає
            # виміряти глибину, тому це не привід віддати помилку замість числа.
            result["metadata"] = None

        # У сучасній схемі обидві колонки часу присутні одночасно, але `start`
        # лишилась порожньою заглушкою CHAR(0). Тому порожній результат по
        # першій колонці означає «не та колонка», а не «немає даних», і треба
        # спробувати наступну; якщо порожні всі - таблиця справді порожня.
        stamps: list[float] = []
        for column in available:
            stamps = _stamps(conn, deadline, column)
            if stamps:
                break
    except sqlite3.DatabaseError as error:
        result["error"] = _classify(error)
        result["detail"] = str(error)
        return result
    finally:
        conn.close()

    result["hours"] = len(stamps)
    if not stamps:
        # Порожня таблиця - не помилка, а найгірший з можливих результатів:
        # глибина нуль. Сторож має віддати нуль, а не «unknown», інакше
        # тривога не спрацює саме в найважливішому випадку.
        result["ok"] = True
        result["depth_days"] = 0
        return result

    oldest, newest = min(stamps), max(stamps)
    days = sorted({_local(stamp, zone).date() for stamp in stamps})
    first, last = days[0], days[-1]
    present = set(days)
    missing = []
    missing_total = 0
    cursor = first
    while cursor <= last:
        if cursor not in present:
            missing_total += 1
            if len(missing) < MISSING_LIMIT:
                missing.append(cursor.isoformat())
        cursor += timedelta(days=1)

    today = datetime.now(timezone.utc).astimezone(zone).date()
    result.update(
        {
            "ok": True,
            "depth_days": len(days),
            "oldest": _local(oldest, zone).isoformat(timespec="seconds"),
            "newest": _local(newest, zone).isoformat(timespec="seconds"),
            "oldest_date": first.isoformat(),
            "newest_date": last.isoformat(),
            "span_days": round((newest - oldest) / 86400.0, 2),
            "lag_days": (today - last).days,
            "missing_days": missing,
            "missing_days_total": missing_total,
        }
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Глибина довгострокової статистики HA")
    parser.add_argument("--db", default=DEFAULT_DB, help="файл бази recorder")
    parser.add_argument(
        "--tz",
        default=DEFAULT_TZ,
        help="пояс IANA для меж доби; порожньо - системна локаль",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="повертати код 1 при помилці; для shell-перевірок, не для HA",
    )
    args = parser.parse_args(argv)

    try:
        result = read_depth(args.db, _zone(args.tz))
    except Exception as error:  # noqa: BLE001 - сторож не має права падати мовчки
        result = _blank(args.db)
        result["error"] = "unexpected"
        result["detail"] = "{0}: {1}".format(type(error).__name__, error)

    print(json.dumps(result, ensure_ascii=False))
    return 1 if args.strict and not result["ok"] else 0


if __name__ == "__main__":
    sys.exit(main())
