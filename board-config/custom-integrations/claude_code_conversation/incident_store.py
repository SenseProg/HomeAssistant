"""Реєстр інцидентів будинку HomeMate.

Окремий від пам'яті сховище-журнал: пам'ять тримає побажання власника («бойлер
гріємо вночі»), а тут лежать **відкриті технічні проблеми**, які ще треба
полагодити, з доказами й статусом. Мета — щоб знахідка на кшталт «нічний полив
недоливає, бо контролер закриває клапан за власним таймером» не жила лише в
одній розмові, а лишалася перед очима і в асистента, і в обслуговчих сесій.

Формат той самий приватний JSONL поруч з історією діалогу, поза `.storage`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
import unicodedata
import uuid

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    INCIDENT_AREAS,
    INCIDENT_SEVERITIES,
    INCIDENT_STATUSES,
    INCIDENTS_MAX_ITEMS,
    INCIDENTS_MAX_TEXT_CHARS,
    INCIDENTS_PROMPT_MAX,
)

# Статуси, які означають «ще не закрито» і тому завжди йдуть у промт.
OPEN_STATUSES = ("open", "watching")


def _normalize(text: object, limit: int = INCIDENTS_MAX_TEXT_CHARS) -> str:
    return unicodedata.normalize("NFC", " ".join(str(text or "").split()))[:limit]


def _pick(value: object, allowed: tuple[str, ...], default: str) -> str:
    candidate = str(value or "").strip().casefold()
    return candidate if candidate in allowed else default


def _read_items(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return items
    for line in lines:
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(record, dict) and isinstance(record.get("title"), str):
            items.append(record)
    return items


def _write_items(path: Path, items: list[dict[str, Any]]) -> None:
    trimmed = sorted(items, key=lambda item: str(item.get("created", "")))
    trimmed = trimmed[-INCIDENTS_MAX_ITEMS:]
    payload = "".join(
        json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
        for item in trimmed
    )
    temporary = path.with_suffix(".jsonl.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, path)
    path.chmod(0o600)


def _sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
    """Спершу відкриті, потім за тяжкістю, потім свіжіші."""
    status_rank = {"open": 0, "watching": 1, "resolved": 2}
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    return (
        status_rank.get(str(item.get("status")), 3),
        severity_rank.get(str(item.get("severity")), 3),
        str(item.get("updated", "")),
    )


def format_incident(item: dict[str, Any], *, full: bool = False) -> str:
    """Один інцидент одним рядком для промта або відповіді у чат."""
    head = (
        f"- `{item.get('id', '?')}` · {item.get('status', '?')}"
        f" · {item.get('severity', '?')} · {item.get('area', 'other')}"
        f" · {item.get('title', '')}"
    )
    if not full:
        detail = _normalize(item.get("detail"), 240)
        return f"{head}\n  {detail}" if detail else head
    parts = [head]
    for label, key in (
        ("деталі", "detail"),
        ("докази", "evidence"),
        ("розв'язання", "resolution"),
    ):
        value = _normalize(item.get(key))
        if value:
            parts.append(f"  {label}: {value}")
    parts.append(
        f"  заведено {item.get('created', '?')[:16]}"
        f" ({item.get('source', 'operator')}),"
        f" оновлено {item.get('updated', '?')[:16]}"
    )
    return "\n".join(parts)


def format_open_incidents(items: list[dict[str, Any]]) -> str:
    """Тіло блоку <known_incidents>: лише незакриті, обмежено за кількістю."""
    active = [item for item in items if item.get("status") in OPEN_STATUSES]
    if not active:
        return "- Відкритих інцидентів немає."
    active.sort(key=_sort_key)
    lines = [format_incident(item) for item in active[:INCIDENTS_PROMPT_MAX]]
    if len(active) > INCIDENTS_PROMPT_MAX:
        lines.append(
            f"- … ще {len(active) - INCIDENTS_PROMPT_MAX};"
            " повний перелік дає інструмент IncidentList."
        )
    return "\n".join(lines)


class IncidentStore:
    """Асинхронна обгортка над приватним JSONL з інцидентами."""

    def __init__(self, hass: HomeAssistant, path: Path, lock) -> None:
        self._hass = hass
        self._path = path
        self._lock = lock

    async def async_list(self) -> list[dict[str, Any]]:
        async with self._lock:
            items = await self._hass.async_add_executor_job(_read_items, self._path)
        items.sort(key=_sort_key)
        return items

    async def async_add(
        self,
        title: str,
        detail: str = "",
        *,
        area: str = "other",
        severity: str = "medium",
        evidence: str = "",
        source: str = "assistant",
    ) -> dict[str, Any]:
        """Завести інцидент. Повертає створений запис."""
        now_iso = dt_util.utcnow().isoformat()
        item = {
            "id": uuid.uuid4().hex[:8],
            "created": now_iso,
            "updated": now_iso,
            "status": "open",
            "severity": _pick(severity, INCIDENT_SEVERITIES, "medium"),
            "area": _pick(area, INCIDENT_AREAS, "other"),
            "title": _normalize(title, 200),
            "detail": _normalize(detail),
            "evidence": _normalize(evidence),
            "resolution": "",
            "source": source,
        }
        async with self._lock:
            items = await self._hass.async_add_executor_job(_read_items, self._path)
            items.append(item)
            await self._hass.async_add_executor_job(_write_items, self._path, items)
        return item

    async def async_update(
        self,
        incident_id: str,
        *,
        status: str | None = None,
        resolution: str | None = None,
        detail: str | None = None,
        severity: str | None = None,
    ) -> dict[str, Any] | None:
        """Оновити статус/розв'язання. Повертає запис або None, якщо не знайдено."""
        async with self._lock:
            items = await self._hass.async_add_executor_job(_read_items, self._path)
            target = next(
                (item for item in items if item.get("id") == incident_id), None
            )
            if target is None:
                return None
            if status is not None:
                target["status"] = _pick(
                    status, INCIDENT_STATUSES, str(target.get("status", "open"))
                )
            if severity is not None:
                target["severity"] = _pick(
                    severity, INCIDENT_SEVERITIES, str(target.get("severity", "medium"))
                )
            if resolution is not None:
                target["resolution"] = _normalize(resolution)
            if detail is not None:
                target["detail"] = _normalize(detail)
            target["updated"] = dt_util.utcnow().isoformat()
            await self._hass.async_add_executor_job(_write_items, self._path, items)
        return target
