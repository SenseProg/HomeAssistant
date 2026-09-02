#!/usr/bin/env python3
"""Журнал показників механічного лічильника свердловини.

Сховище — простий JSON-файл поруч із конфігурацією Home Assistant. Він обраний
замість двадцяти чотирьох слотів `input_text` свідомо: слоти обмежені числом
і довжиною, не тримають історії редагувань і, як показав перезапуск
21.08.2026, можуть не пережити падіння HA, бо `.storage/core.restore_state`
пишеться періодично. Звичайний файл переживає рестарт і потрапляє у бекап
конфігурації.

Запис ніколи не втрачає попереднє значення: правка складає стару версію в
`revisions`, а видалення лише виставляє `deleted`. Фізично рядок не зникає.

Команди:
    export  [--limit N] [--include-deleted]   JSON для command_line-сенсора
    add     --iso --value --author [--note]
    edit    --id [--iso] [--value] [--author] [--note] --by
    delete  --id --by
    restore --id --by
    import-legacy --json '<[[iso, value, author], ...]>'

Запис атомарний: тимчасовий файл + os.replace, плюс дата-штампована копія
попереднього вмісту в `backups/`.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import sys
from datetime import datetime, timezone

STORE = os.environ.get(
    "WATER_READINGS_STORE",
    "/userdata/hass/config/water_readings.json",
)
# Свідомо НЕ config/backups: та тека — мережевий монтаж на NAS і водночас
# сховище власних архівів Home Assistant. Копія показників туди означала б,
# що недоступний NAS блокує збереження показника, а самі копії пакувалися б
# у кожен архів HA. Тримаємо їх поруч зі сховищем, на локальному диску.
BACKUP_DIR = os.path.join(os.path.dirname(STORE), "water_readings_history")
KEEP_BACKUPS = 20
VERSION = 2

# Базова точка й енергетична поправка донедавна були вписані дослівно у чотири
# автоматизації, три картки та обидва YAML-дашборди - разом більш ніж десяток
# місць на два числа. Після ремонту телеметрії LocalTuya калібрування доведеться
# перезняти, і будь-яке пропущене місце тоді почне тихо брехати. Тому числа
# живуть тут, поруч із показниками, і роздаються через той самий сенсор.
DEFAULT_CALIBRATION = {
    "baseline_value": 814.79,
    "baseline_iso": "2026-08-20T23:23:18+03:00",
    "energy_offset_kwh": 0.01748706,
    "note": (
        "Механічна база після першого зафіксованого пуску насоса. Поправка - "
        "енергія, спожита після цієї точки, але до появи власного інтегратора."
    ),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load() -> dict:
    if not os.path.isfile(STORE):
        return {
            "version": VERSION,
            "updated_at": None,
            "calibration": dict(DEFAULT_CALIBRATION),
            "readings": [],
        }
    with open(STORE, encoding="utf-8") as handle:
        data = json.load(handle)
    data.setdefault("version", VERSION)
    data.setdefault("readings", [])
    # Міграція v1 -> v2: у старому файлі секції калібрування не було зовсім.
    calibration = data.setdefault("calibration", {})
    for key, value in DEFAULT_CALIBRATION.items():
        calibration.setdefault(key, value)
    return data


def backup() -> None:
    """Зняти копію попереднього вмісту. Помилка тут не має зривати запис.

    Копія — приємність, а введений показник — те, заради чого людина відкрила
    сторінку. Якщо диск переповнений або тека недоступна, доречніше зберегти
    показник без копії й сказати про це в результаті, ніж втратити і те, і те.
    """
    if not os.path.isfile(STORE):
        return
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(STORE, os.path.join(BACKUP_DIR, f"water_readings.{stamp}.json"))
        for stale in sorted(os.listdir(BACKUP_DIR), reverse=True)[KEEP_BACKUPS:]:
            os.remove(os.path.join(BACKUP_DIR, stale))
    except OSError as error:
        print(
            json.dumps({"warning": "backup_failed", "detail": str(error)}, ensure_ascii=False),
            file=sys.stderr,
        )


def save(data: dict) -> None:
    backup()
    data["version"] = VERSION
    data["updated_at"] = now_iso()
    data["readings"].sort(key=lambda row: row.get("iso", ""))
    temp = f"{STORE}.tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, STORE)


def make_id(iso: str) -> str:
    digits = "".join(char for char in iso if char.isdigit())
    return f"r-{digits[:14]}"


def unique_id(data: dict, iso: str) -> str:
    base = make_id(iso)
    taken = {row["id"] for row in data["readings"]}
    if base not in taken:
        return base
    for suffix in range(2, 1000):
        candidate = f"{base}-{suffix}"
        if candidate not in taken:
            return candidate
    raise SystemExit("не вдалося підібрати унікальний ідентифікатор")


def find(data: dict, reading_id: str) -> dict:
    for row in data["readings"]:
        if row["id"] == reading_id:
            return row
    raise SystemExit(f"запис {reading_id} не знайдено")


def snapshot(row: dict) -> dict:
    return {
        "iso": row.get("iso"),
        "value": row.get("value"),
        "author": row.get("author"),
        "note": row.get("note", ""),
    }


def cmd_add(args: argparse.Namespace) -> dict:
    data = load()
    row = {
        "id": unique_id(data, args.iso),
        "iso": args.iso,
        "value": round(float(args.value), 3),
        "author": args.author or "Користувач",
        "note": args.note or "",
        "deleted": False,
        "deleted_at": None,
        "deleted_by": None,
        "created_at": now_iso(),
        "updated_at": None,
        "revisions": [],
    }
    data["readings"].append(row)
    save(data)
    return {"ok": True, "action": "add", "id": row["id"]}


def cmd_edit(args: argparse.Namespace) -> dict:
    data = load()
    row = find(data, args.id)
    before = snapshot(row)
    if args.iso:
        row["iso"] = args.iso
    if args.value is not None:
        row["value"] = round(float(args.value), 3)
    if args.author:
        row["author"] = args.author
    if args.note is not None:
        row["note"] = args.note
    after = snapshot(row)
    if after == before:
        return {"ok": True, "action": "edit", "id": row["id"], "changed": False}
    row.setdefault("revisions", []).append(
        {"at": now_iso(), "by": args.by or "Користувач", "from": before}
    )
    row["updated_at"] = now_iso()
    save(data)
    return {"ok": True, "action": "edit", "id": row["id"], "changed": True}


def cmd_delete(args: argparse.Namespace) -> dict:
    data = load()
    row = find(data, args.id)
    if not row.get("deleted"):
        row["deleted"] = True
        row["deleted_at"] = now_iso()
        row["deleted_by"] = args.by or "Користувач"
        save(data)
    return {"ok": True, "action": "delete", "id": row["id"]}


def cmd_restore(args: argparse.Namespace) -> dict:
    data = load()
    row = find(data, args.id)
    if row.get("deleted"):
        row.setdefault("revisions", []).append(
            {"at": now_iso(), "by": args.by or "Користувач", "restored_from_deleted": True}
        )
        row["deleted"] = False
        row["deleted_at"] = None
        row["deleted_by"] = None
        save(data)
    return {"ok": True, "action": "restore", "id": row["id"]}


def cmd_import_legacy(args: argparse.Namespace) -> dict:
    data = load()
    existing = {(row["iso"], row["value"]) for row in data["readings"]}
    added = 0
    for entry in json.loads(args.json):
        iso, value = entry[0], round(float(entry[1]), 3)
        author = entry[2] if len(entry) > 2 else "Excel"
        if (iso, value) in existing:
            continue
        data["readings"].append(
            {
                "id": unique_id(data, iso),
                "iso": iso,
                "value": value,
                "author": author,
                "note": "",
                "deleted": False,
                "deleted_at": None,
                "deleted_by": None,
                "created_at": now_iso(),
                "updated_at": None,
                "revisions": [],
            }
        )
        existing.add((iso, value))
        added += 1
    if added:
        save(data)
    return {"ok": True, "action": "import-legacy", "added": added}


def cmd_export(args: argparse.Namespace) -> dict:
    data = load()
    rows = data["readings"]
    if not args.include_deleted:
        rows = [row for row in rows if not row.get("deleted")]
    rows = sorted(rows, key=lambda row: row.get("iso", ""))
    total = len(rows)
    if args.limit and args.limit > 0:
        rows = rows[-args.limit :]
    compact = [
        {
            "id": row["id"],
            "iso": row["iso"],
            "value": row["value"],
            "author": row.get("author", ""),
            "note": row.get("note", ""),
            "deleted": bool(row.get("deleted")),
            "edited": bool(row.get("revisions")),
            "revisions": len(row.get("revisions", [])),
        }
        for row in rows
    ]
    return {
        "count": total,
        "shown": len(compact),
        "updated_at": data.get("updated_at"),
        "calibration": data.get("calibration", dict(DEFAULT_CALIBRATION)),
        "readings": compact,
    }


def cmd_calibration(args: argparse.Namespace) -> dict:
    """Прочитати або змінити базову точку та енергетичну поправку."""
    data = load()
    calibration = data["calibration"]
    # load() домальовує секцію дефолтами, але на диск вона потрапляє лише разом
    # із якимось записом. Поки цього не сталося, значення живуть у коді, а не в
    # сховищі — і мовчки поїхали б, якби дефолти колись змінили. Тому файл без
    # секції дописуємо одразу, навіть коли міняти нічого не просили.
    on_disk = {}
    if os.path.isfile(STORE):
        with open(STORE, encoding="utf-8") as handle:
            on_disk = json.load(handle)
    changed = "calibration" not in on_disk
    for field, value in (
        ("baseline_value", args.baseline_value),
        ("baseline_iso", args.baseline_iso),
        ("energy_offset_kwh", args.energy_offset_kwh),
        ("note", args.note),
    ):
        if value in (None, ""):
            continue
        new = float(value) if field != "baseline_iso" and field != "note" else value
        if calibration.get(field) != new:
            calibration.setdefault("history", [])
            calibration["history"].append(
                {"at": now_iso(), "field": field, "from": calibration.get(field)}
            )
            calibration[field] = new
            changed = True
    if changed:
        save(data)
    return {"ok": True, "action": "calibration", "changed": changed, "calibration": calibration}


def cmd_apply(args: argparse.Namespace) -> dict:
    """Виконати дію, описану в base64(JSON).

    Home Assistant рендерить `shell_command` у рядок і лише потім розбиває його
    через shlex. Якби ім'я автора чи нотатка потрапляли туди дослівно, лапка або
    крапка з комою ламала б команду. Base64 містить тільки безпечні символи, тож
    вся структура доїжджає цілою і розбирається вже тут.
    """
    raw = base64.b64decode(args.payload).decode("utf-8")
    body = json.loads(raw)
    action = body.get("action")
    handlers = {
        "add": (cmd_add, ("iso", "value", "author", "note")),
        "edit": (cmd_edit, ("id", "iso", "value", "author", "note", "by")),
        "delete": (cmd_delete, ("id", "by")),
        "restore": (cmd_restore, ("id", "by")),
        "calibration": (
            cmd_calibration,
            ("baseline_value", "baseline_iso", "energy_offset_kwh", "note"),
        ),
    }
    if action not in handlers:
        raise ValueError(f"невідома дія: {action!r}")
    handler, fields = handlers[action]
    namespace = argparse.Namespace(**{field: body.get(field) for field in fields})
    for field in ("author", "note", "by", "iso"):
        if field in fields and getattr(namespace, field, None) is None:
            setattr(namespace, field, "")
    return handler(namespace)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export")
    export.add_argument("--limit", type=int, default=0)
    export.add_argument("--include-deleted", action="store_true")
    export.set_defaults(func=cmd_export)

    add = sub.add_parser("add")
    add.add_argument("--iso", required=True)
    add.add_argument("--value", required=True)
    add.add_argument("--author", default="")
    add.add_argument("--note", default="")
    add.set_defaults(func=cmd_add)

    edit = sub.add_parser("edit")
    edit.add_argument("--id", required=True)
    edit.add_argument("--iso", default="")
    edit.add_argument("--value", default=None)
    edit.add_argument("--author", default="")
    edit.add_argument("--note", default=None)
    edit.add_argument("--by", default="")
    edit.set_defaults(func=cmd_edit)

    delete = sub.add_parser("delete")
    delete.add_argument("--id", required=True)
    delete.add_argument("--by", default="")
    delete.set_defaults(func=cmd_delete)

    restore = sub.add_parser("restore")
    restore.add_argument("--id", required=True)
    restore.add_argument("--by", default="")
    restore.set_defaults(func=cmd_restore)

    legacy = sub.add_parser("import-legacy")
    legacy.add_argument("--json", required=True)
    legacy.set_defaults(func=cmd_import_legacy)

    calibration = sub.add_parser("calibration")
    calibration.add_argument("--baseline-value", default=None)
    calibration.add_argument("--baseline-iso", default=None)
    calibration.add_argument("--energy-offset-kwh", default=None)
    calibration.add_argument("--note", default=None)
    calibration.set_defaults(func=cmd_calibration)

    apply_cmd = sub.add_parser(
        "apply",
        help="виконати дію з base64(JSON); так HA передає значення без ризику "
        "shell-ін'єкції, бо payload складається лише з [A-Za-z0-9+/=]",
    )
    apply_cmd.add_argument("--payload", required=True)
    apply_cmd.set_defaults(func=cmd_apply)

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
