"""Project-local MCP server for safe Home Assistant administration."""

from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP

from project_tools import (
    board_health,
    git_status,
    incidents,
    irrigation_health,
    network_inventory,
    project_summary,
    recent_logs,
    repo_board_sync,
    validate_config,
)


mcp = FastMCP("home-assistant-project")


@mcp.tool()
def ha_project_summary() -> dict:
    """Return canonical project paths, protected data, and sync targets."""
    return project_summary()


@mcp.tool()
def ha_board_health() -> dict:
    """Read HA service/HTTP, uptime, disk, zram, journal cap, and timer state."""
    return board_health()


@mcp.tool()
def ha_irrigation_health() -> dict:
    """Check controller and pump LocalTuya readiness without moving hardware."""
    return irrigation_health()


@mcp.tool()
def ha_repo_board_sync(files: Optional[list[str]] = None) -> dict:
    """Compare allow-listed Git files with the board by SHA-256; never copy files."""
    return repo_board_sync(files)


@mcp.tool()
def ha_validate_config() -> dict:
    """Run Home Assistant check_config on the board without restarting it."""
    return validate_config()


@mcp.tool()
def ha_recent_logs(lines: int = 100, pattern: Optional[str] = None) -> dict:
    """Read up to 1000 recent HA journal lines, optionally filtered locally."""
    return recent_logs(lines, pattern)


@mcp.tool()
def ha_git_status() -> dict:
    """Read current branch, upstream divergence, and working-tree status."""
    return git_status()


@mcp.tool()
def ha_incidents(status: str = "open") -> dict:
    """Read the board incident register: open (default), resolved, or all."""
    return incidents(status)


@mcp.tool()
def ha_network_inventory(query: Optional[str] = None) -> dict:
    """List or search fixed LAN devices by IP, MAC, hostname, or function."""
    return network_inventory(query)


if __name__ == "__main__":
    mcp.run(transport="stdio")
