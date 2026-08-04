"""Authenticated WebSocket API for the persistent Claude transcript."""

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from . import ClaudeCodeConfigEntry
from .const import DOMAIN
from .history_store import async_recent_records


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


def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register the integration WebSocket commands."""
    websocket_api.async_register_command(hass, websocket_history)
