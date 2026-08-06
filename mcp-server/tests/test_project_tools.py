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


def test_irrigation_health_requires_localtuya_and_expected_mac(monkeypatch) -> None:
    stdout = """ha_service=active
ha_http=200
controller_ping=ok
controller_neighbor=192.168.50.221 dev eth1 lladdr 38:2c:e5:2d:5b:32 REACHABLE
controller_localtuya=established
pump_ping=ok
pump_neighbor=192.168.50.91 dev eth1 lladdr 80:64:7c:46:e8:d1 REACHABLE
pump_localtuya=established
controller_errors_10m=0
pump_errors_10m=0
"""
    monkeypatch.setattr(
        project_tools,
        "_ssh",
        lambda command, timeout=30: {
            "ok": True,
            "returncode": 0,
            "stdout": stdout,
            "stderr": "",
        },
    )

    result = project_tools.irrigation_health()

    assert result["controller_ready"] is True
    assert result["irrigation_ready"] is True
    assert result["control_path"].startswith("LocalTuya")


def test_irrigation_health_rejects_ping_only_controller(monkeypatch) -> None:
    stdout = """ha_service=active
ha_http=200
controller_ping=ok
controller_neighbor=192.168.50.221 dev eth1 lladdr 38:2c:e5:2d:5b:32 REACHABLE
controller_localtuya=disconnected
pump_ping=ok
pump_neighbor=192.168.50.91 dev eth1 lladdr 80:64:7c:46:e8:d1 REACHABLE
pump_localtuya=established
controller_errors_10m=1
pump_errors_10m=0
"""
    monkeypatch.setattr(
        project_tools,
        "_ssh",
        lambda command, timeout=30: {
            "ok": True,
            "returncode": 0,
            "stdout": stdout,
            "stderr": "",
        },
    )

    result = project_tools.irrigation_health()

    assert result["controller_ready"] is False
    assert result["irrigation_ready"] is False
