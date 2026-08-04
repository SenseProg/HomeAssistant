"""Authenticated WebSocket APIs for Claude transcript and voice recordings."""

from pathlib import Path
from typing import Any
import wave

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from . import ClaudeCodeConfigEntry
from .const import DOMAIN, VOICE_RECORDING_DIR, VOICE_RECORDING_LIST_LIMIT
from .history_store import async_recent_records
from .http_api import encode_recording_id


def _active_entry(hass: HomeAssistant) -> ClaudeCodeConfigEntry | None:
    """Return the first loaded Claude Code config entry."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            return entry
    return None


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/history",
        vol.Optional("limit", default=200): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=500)
        ),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_history(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the bounded persistent conversation transcript."""
    entry = _active_entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_loaded", "Claude agent is not loaded")
        return

    records = await async_recent_records(hass, entry, msg["limit"])
    connection.send_result(msg["id"], {"records": records})


def _recording_duration(path: Path) -> float:
    """Return WAV duration in seconds, or zero for an invalid file."""
    try:
        with wave.open(str(path), "rb") as recording:
            rate = recording.getframerate()
            return recording.getnframes() / rate if rate else 0
    except (OSError, EOFError, wave.Error):
        return 0


def _voice_recordings() -> list[dict[str, Any]]:
    """Return the newest private WAV recordings with bounded metadata."""
    root = Path(VOICE_RECORDING_DIR)
    if not root.is_dir():
        return []

    files = sorted(
        (path for path in root.rglob("*.wav") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:VOICE_RECORDING_LIST_LIMIT]
    result: list[dict[str, Any]] = []
    for path in files:
        stat = path.stat()
        result.append(
            {
                "id": encode_recording_id(path),
                "created": stat.st_mtime,
                "duration": round(_recording_duration(path), 2),
                "size": stat.st_size,
            }
        )
    return result


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/voice_recordings"}
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_voice_recordings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return metadata for private archived voice messages."""
    recordings = await hass.async_add_executor_job(_voice_recordings)
    connection.send_result(msg["id"], {"recordings": recordings})


def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register the integration WebSocket commands."""
    websocket_api.async_register_command(hass, websocket_history)
    websocket_api.async_register_command(hass, websocket_voice_recordings)
