"""Config flow for Claude Code Conversation."""

import asyncio
import json
import os
from typing import Any, override

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_MODEL, CONF_NAME, CONF_PROMPT
from homeassistant.helpers.selector import TemplateSelector

from .const import (
    CLAUDE_PATH,
    CONF_MAX_HISTORY,
    CONF_TIMEOUT,
    DEFAULT_MAX_HISTORY,
    DEFAULT_MODEL,
    DEFAULT_NAME,
    DEFAULT_PROMPT,
    DEFAULT_TIMEOUT,
    DOMAIN,
)


async def _async_validate_claude() -> None:
    """Verify that Claude Code exists and subscription auth is active."""
    env = os.environ.copy()
    env["HOME"] = "/home/forlinx"
    process = await asyncio.create_subprocess_exec(
        CLAUDE_PATH,
        "auth",
        "status",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    async with asyncio.timeout(15):
        stdout, _stderr = await process.communicate()
    if process.returncode != 0:
        raise ConnectionError
    try:
        status = json.loads(stdout)
    except (json.JSONDecodeError, UnicodeDecodeError) as err:
        raise ConnectionError from err
    if not status.get("loggedIn") or status.get("authMethod") != "claude.ai":
        raise PermissionError


class ClaudeCodeConversationConfigFlow(
    config_entries.ConfigFlow, domain=DOMAIN
):
    """Handle a config flow for Claude Code Conversation."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the local Claude Code conversation agent."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await _async_validate_claude()
            except PermissionError:
                errors["base"] = "not_authenticated"
            except (ConnectionError, FileNotFoundError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                title = user_input.pop(CONF_NAME)
                return self.async_create_entry(title=title, data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_MODEL, default=DEFAULT_MODEL): vol.In(
                    ["sonnet", "opus"]
                ),
                vol.Required(CONF_PROMPT, default=DEFAULT_PROMPT): TemplateSelector(),
                vol.Required(
                    CONF_MAX_HISTORY, default=DEFAULT_MAX_HISTORY
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
                vol.Required(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(
                    vol.Coerce(int), vol.Range(min=30, max=300)
                ),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors or None
        )
