"""Private persistent transcript storage for Claude Code Conversation."""

from collections.abc import Iterable
from datetime import timedelta
import json
import os
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import ClaudeCodeConfigEntry
from .const import HISTORY_MAX_RECORDS, HISTORY_RETENTION_DAYS


def _read_records(path: Path) -> list[dict[str, Any]]:
    """Read valid JSONL records without failing the conversation on one bad line."""
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return records

    for line in lines:
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if (
            isinstance(record, dict)
            and record.get("role") in {"user", "assistant"}
            and isinstance(record.get("content"), str)
            and isinstance(record.get("timestamp"), str)
        ):
            records.append(record)
    return records


def _trim_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply disk-retention limits to transcript records."""
    cutoff = dt_util.utcnow() - timedelta(days=HISTORY_RETENTION_DAYS)
    kept: list[dict[str, Any]] = []
    for record in records:
        timestamp = dt_util.parse_datetime(record["timestamp"])
        if timestamp is None or dt_util.as_utc(timestamp) < cutoff:
            continue
        kept.append(record)
    return kept[-HISTORY_MAX_RECORDS:]


def _write_records(path: Path, records: list[dict[str, Any]]) -> None:
    """Atomically replace the private JSONL transcript."""
    temporary = path.with_suffix(".jsonl.tmp")
    payload = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    temporary.write_text(payload, encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, path)
    path.chmod(0o600)


async def async_recent_records(
    hass: HomeAssistant,
    entry: ClaudeCodeConfigEntry,
    limit: int,
) -> list[dict[str, Any]]:
    """Load recent messages for cross-session conversational context."""
    runtime = entry.runtime_data
    async with runtime.history_lock:
        records = await hass.async_add_executor_job(
            _read_records, runtime.history_path
        )
    return _trim_records(records)[-limit:]


async def async_append_exchange(
    hass: HomeAssistant,
    entry: ClaudeCodeConfigEntry,
    conversation_id: str | None,
    user_text: str,
    assistant_text: str,
) -> None:
    """Persist one complete user/assistant exchange."""
    timestamp = dt_util.utcnow().isoformat()
    new_records = (
        {
            "timestamp": timestamp,
            "conversation_id": conversation_id,
            "role": "user",
            "content": user_text,
        },
        {
            "timestamp": timestamp,
            "conversation_id": conversation_id,
            "role": "assistant",
            "content": assistant_text,
        },
    )
    runtime = entry.runtime_data
    async with runtime.history_lock:
        records = await hass.async_add_executor_job(
            _read_records, runtime.history_path
        )
        records.extend(new_records)
        records = _trim_records(records)
        await hass.async_add_executor_job(
            _write_records, runtime.history_path, records
        )
