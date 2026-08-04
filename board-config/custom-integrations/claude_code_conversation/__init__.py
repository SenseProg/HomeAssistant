"""Claude Code Conversation integration."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, HISTORY_FILE

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = (Platform.CONVERSATION,)
FRONTEND_DIR = Path(__file__).parent / "frontend"
FRONTEND_URL = "/claude_code_conversation_static"

@dataclass(slots=True)
class ClaudeCodeRuntimeData:
    """Runtime locks and the private persistent conversation store."""

    claude_lock: asyncio.Lock
    history_lock: asyncio.Lock
    history_path: Path
    system_lock: asyncio.Lock
    system_snapshot: str | None
    system_snapshot_monotonic: float


type ClaudeCodeConfigEntry = ConfigEntry[ClaudeCodeRuntimeData]


def _ensure_private_history_file(path: Path) -> None:
    """Create the history store outside Home Assistant's .storage directory."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration domain."""
    from .websocket_api import async_register_websocket_api

    async_register_websocket_api(hass)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL, str(FRONTEND_DIR), cache_headers=False)]
    )
    await panel_custom.async_register_panel(
        hass=hass,
        frontend_url_path="claude-home",
        webcomponent_name="claude-history-panel",
        sidebar_title="Claude чат",
        sidebar_icon="mdi:message-text-clock-outline",
        module_url=f"{FRONTEND_URL}/claude-history-panel.js?v=0.3.0",
        embed_iframe=False,
        require_admin=True,
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: ClaudeCodeConfigEntry
) -> bool:
    """Set up Claude Code from a config entry."""
    history_path = Path(HISTORY_FILE)
    await hass.async_add_executor_job(_ensure_private_history_file, history_path)
    entry.runtime_data = ClaudeCodeRuntimeData(
        claude_lock=asyncio.Lock(),
        history_lock=asyncio.Lock(),
        history_path=history_path,
        system_lock=asyncio.Lock(),
        system_snapshot=None,
        system_snapshot_monotonic=0.0,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ClaudeCodeConfigEntry
) -> bool:
    """Unload a Claude Code config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
