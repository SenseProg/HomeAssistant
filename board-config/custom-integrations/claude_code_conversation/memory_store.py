"""Постійна пам'ять фактів для домашнього асистента Claude.

Дизайн запозичено з ai-subscription-assist (MIT, Jackson Tomlinson) і свідомо
спрощено: без векторних вкладень, лише лексична схожість плюс свіжість.
Файл — приватний JSONL поруч з історією діалогу, поза `.storage`.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import re
from typing import Any
import unicodedata
import uuid

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import MEMORY_MAX_ITEMS, MEMORY_RECALL_TOP_K

_WORD_RE = re.compile(r"[\w']+", re.UNICODE)

# Фрази, якими користувач просить щось запам'ятати. Текст факту — те, що далі.
_REMEMBER_RE = re.compile(
    r"^\s*(?:запам['’]?ятай|запамятай|remember)[\s,:-]+(?:що\s+|that\s+)?(?P<fact>.+)$",
    re.IGNORECASE | re.DOTALL,
)

# Пам'ять зберігається у відкритому файлі і підмішується в промти, тому
# секрети туди потрапляти не повинні незалежно від прохання користувача.
_SENSITIVE_MARKERS = (
    "парол",
    "password",
    "пін",
    "pin-код",
    "pin code",
    "token",
    "токен",
    "api key",
    "апі ключ",
    "cvv",
    "секрет",
)


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFC", " ".join(text.split()))


def _tokens(text: str) -> set[str]:
    return {
        token.casefold()
        for token in _WORD_RE.findall(text)
        if len(token) >= 3
    }


def extract_remember_request(text: str) -> str | None:
    """Return the fact to store when the message is a remember command."""
    match = _REMEMBER_RE.match(text)
    if not match:
        return None
    fact = _normalize(match.group("fact")).strip(".!? ")
    return fact or None


def looks_sensitive(text: str) -> bool:
    """Reject facts that look like credentials or other secrets."""
    lowered = text.casefold()
    return any(marker in lowered for marker in _SENSITIVE_MARKERS)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _recency_score(updated: str, now: datetime) -> float:
    """Exponential decay with a 30-day half-life."""
    parsed = dt_util.parse_datetime(updated)
    if parsed is None:
        return 0.0
    age_days = max(0.0, (now - dt_util.as_utc(parsed)) / timedelta(days=1))
    return 0.5 ** (age_days / 30)


def rank_memories(
    items: list[dict[str, Any]], query: str, top_k: int = MEMORY_RECALL_TOP_K
) -> list[dict[str, Any]]:
    """Return the most relevant facts for the query, best first."""
    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    now = dt_util.utcnow()
    scored: list[tuple[float, dict[str, Any]]] = []
    for item in items:
        text = str(item.get("text", ""))
        lexical = _jaccard(query_tokens, _tokens(text))
        if lexical <= 0:
            continue
        score = 0.7 * lexical + 0.3 * _recency_score(
            str(item.get("updated", "")), now
        )
        scored.append((score, item))
    scored.sort(key=lambda pair: -pair[0])
    return [item for _score, item in scored[:top_k]]


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
        if isinstance(record, dict) and isinstance(record.get("text"), str):
            items.append(record)
    return items


def _write_items(path: Path, items: list[dict[str, Any]]) -> None:
    trimmed = sorted(items, key=lambda item: str(item.get("updated", "")))
    trimmed = trimmed[-MEMORY_MAX_ITEMS:]
    payload = "".join(
        json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
        for item in trimmed
    )
    temporary = path.with_suffix(".jsonl.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, path)
    path.chmod(0o600)


class MemoryStore:
    """Async wrapper around the private JSONL memory file."""

    def __init__(self, hass: HomeAssistant, path: Path, lock) -> None:
        self._hass = hass
        self._path = path
        self._lock = lock

    async def async_list(self) -> list[dict[str, Any]]:
        async with self._lock:
            return await self._hass.async_add_executor_job(_read_items, self._path)

    async def async_remember(self, fact: str) -> tuple[dict[str, Any], bool]:
        """Store the fact, merging near-duplicates. Returns (item, created)."""
        fact = _normalize(fact)
        now_iso = dt_util.utcnow().isoformat()
        async with self._lock:
            items = await self._hass.async_add_executor_job(
                _read_items, self._path
            )
            fact_tokens = _tokens(fact)
            for item in items:
                if _jaccard(fact_tokens, _tokens(str(item.get("text", "")))) >= 0.6:
                    item["text"] = fact
                    item["updated"] = now_iso
                    await self._hass.async_add_executor_job(
                        _write_items, self._path, items
                    )
                    return item, False
            item = {
                "id": uuid.uuid4().hex[:8],
                "text": fact,
                "created": now_iso,
                "updated": now_iso,
            }
            items.append(item)
            await self._hass.async_add_executor_job(_write_items, self._path, items)
            return item, True

    async def async_forget(self, memory_id: str) -> bool:
        async with self._lock:
            items = await self._hass.async_add_executor_job(
                _read_items, self._path
            )
            kept = [item for item in items if item.get("id") != memory_id]
            if len(kept) == len(items):
                return False
            await self._hass.async_add_executor_job(_write_items, self._path, kept)
            return True

    async def async_clear(self) -> int:
        async with self._lock:
            items = await self._hass.async_add_executor_job(
                _read_items, self._path
            )
            await self._hass.async_add_executor_job(_write_items, self._path, [])
            return len(items)
