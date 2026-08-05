from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import project_tools


def test_inventory_has_unique_ip_and_mac() -> None:
    result = project_tools.network_inventory()
    devices = result["devices"]
    assert result["count"] == 20
    assert len({device["ip"] for device in devices}) == len(devices)
    assert len({device["mac"] for device in devices}) == len(devices)


def test_inventory_finds_deye_by_mac() -> None:
    result = project_tools.network_inventory("D4-27-87-50-23-6C")
    assert result["count"] == 1
    assert result["devices"][0]["hostname"] == "Deye-Inverter"


def test_resolve_targets_rejects_arbitrary_paths() -> None:
    with pytest.raises(ValueError):
        project_tools.resolve_targets(["board-config/secrets.yaml"])


def test_mcp_config_contains_no_credentials() -> None:
    config_path = Path(__file__).resolve().parents[2] / ".mcp.json"
    raw = config_path.read_text(encoding="utf-8")
    config = json.loads(raw)
    assert "password" not in raw.casefold()
    assert "token" not in raw.casefold()
    assert "home-assistant-project" in config["mcpServers"]
