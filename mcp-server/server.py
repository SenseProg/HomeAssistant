"""Project-local MCP server for safe Home Assistant administration."""

from __future__ import annotations

import asyncio
from typing import Optional

from mcp.server.fastmcp import FastMCP

from project_tools import (
    board_health,
    energy_flow_health,
    entity_states,
    git_status,
    incidents,
    irrigation_health,
    network_inventory,
    notify_log,
    project_summary,
    recent_logs,
    repo_board_sync,
    validate_config,
    well_pump_health,
)


mcp = FastMCP("home-assistant-project")

# Кожен інструмент - async-обгортка над синхронною функцією в окремому потоці.
# До 02.09.2026 функції були синхронними і блокували event loop сервера:
# паралельні виклики шикувались у чергу, їхні таймаути сумувались, і навіть
# ha_git_status (який на плату не ходить) чекав 1800 с, поки SSH-інструменти
# перед ним відпрацьовували свої 30-150 с. Виглядало як мертва плата при
# живому SSH.


@mcp.tool()
async def ha_project_summary() -> dict:
    """Return canonical project paths, protected data, and sync targets."""
    return await asyncio.to_thread(project_summary)


@mcp.tool()
async def ha_board_health() -> dict:
    """Read HA, disk, filesystem errors, backup age/size, tailscale, inverter and pump reachability; `problems` lists what is wrong."""
    return await asyncio.to_thread(board_health)


@mcp.tool()
async def ha_irrigation_health() -> dict:
    """Check controller and pump LocalTuya readiness without moving hardware."""
    return await asyncio.to_thread(irrigation_health)


@mcp.tool()
async def ha_well_pump_health() -> dict:
    """Check well-pump LocalTuya readiness without switching the pump."""
    return await asyncio.to_thread(well_pump_health)


@mcp.tool()
async def ha_energy_flow_health() -> dict:
    """Check whole-grid, Deye-branch, and outside-inverter power balance."""
    return await asyncio.to_thread(energy_flow_health)


@mcp.tool()
async def ha_repo_board_sync(files: Optional[list[str]] = None) -> dict:
    """Compare allow-listed Git files with the board by SHA-256; never copy files."""
    return await asyncio.to_thread(repo_board_sync, files)


@mcp.tool()
async def ha_validate_config() -> dict:
    """Run Home Assistant check_config on the board without restarting it."""
    return await asyncio.to_thread(validate_config)


@mcp.tool()
async def ha_recent_logs(lines: int = 100, pattern: Optional[str] = None) -> dict:
    """Read up to 1000 recent HA journal lines, optionally filtered locally."""
    return await asyncio.to_thread(recent_logs, lines, pattern)


@mcp.tool()
async def ha_git_status() -> dict:
    """Read current branch, upstream divergence, and working-tree status."""
    return await asyncio.to_thread(git_status)


@mcp.tool()
async def ha_incidents(status: str = "open") -> dict:
    """Read the board incident register: open (default), resolved, or all."""
    return await asyncio.to_thread(incidents, status)


@mcp.tool()
async def ha_network_inventory(query: Optional[str] = None) -> dict:
    """List or search fixed LAN devices by IP, MAC, hostname, or function."""
    return await asyncio.to_thread(network_inventory, query)


@mcp.tool()
async def ha_entity_states(pattern: str, limit: int = 200) -> dict:
    """Read entity states matching a regex (entity_id or name) via HA's REST API; no attributes, no secrets."""
    return await asyncio.to_thread(entity_states, pattern, limit)


@mcp.tool()
async def ha_notify_log(limit: int = 40) -> dict:
    """Read the board's notification journal: unread count and the latest merged entries."""
    return await asyncio.to_thread(notify_log, limit)


if __name__ == "__main__":
    mcp.run(transport="stdio")
