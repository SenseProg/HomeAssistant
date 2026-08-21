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
    assert result["count"] == 21
    assert len({device["ip"] for device in devices}) == len(devices)
    assert len({device["mac"] for device in devices}) == len(devices)


def test_inventory_finds_deye_by_mac() -> None:
    result = project_tools.network_inventory("D4-27-87-50-23-6C")
    assert result["count"] == 1
    assert result["devices"][0]["hostname"] == "Deye-Inverter"


def test_inventory_finds_well_pump_by_ip() -> None:
    result = project_tools.network_inventory("192.168.50.26")
    assert result["count"] == 1
    assert result["devices"][0]["hostname"] == "Well-Pump"


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


def test_well_pump_health_requires_localtuya_and_expected_mac(monkeypatch) -> None:
    stdout = """ha_service=active
ha_http=200
well_pump_ping=ok
well_pump_neighbor=192.168.50.26 dev eth1 lladdr 86:0f:3b:0a:36:91 REACHABLE
well_pump_localtuya=established
well_pump_errors_10m=0
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

    result = project_tools.well_pump_health()

    assert result["well_pump_ready"] is True
    assert result["expected_scan_interval_seconds"] == 1
    assert result["entities"]["power"] == "sensor.t34_smart_plug_power"
    assert result["entities"]["power_local"] == "sensor.t34_smart_plug_power_2"


def test_well_pump_health_rejects_cloud_only_reachability(monkeypatch) -> None:
    stdout = """ha_service=active
ha_http=200
well_pump_ping=ok
well_pump_neighbor=192.168.50.26 dev eth1 lladdr 86:0f:3b:0a:36:91 REACHABLE
well_pump_localtuya=disconnected
well_pump_errors_10m=0
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

    result = project_tools.well_pump_health()

    assert result["well_pump_ready"] is False


def test_energy_flow_health_splits_whole_site_from_deye(monkeypatch) -> None:
    states = {
        "sensor.zagalne_navantazhennia": {
            "state": "1.55", "unit": "kW", "last_updated": "2026-08-21T07:00:00Z"
        },
        "sensor.merezha_potuzhnist_usogo_vvodu": {
            "state": "1550", "unit": "W", "last_updated": "2026-08-21T07:00:00Z"
        },
        "sensor.inverter_grid_power": {
            "state": "803", "unit": "W", "last_updated": "2026-08-21T07:00:00Z"
        },
        "sensor.spozhivannia_poza_invertorom": {
            "state": "747", "unit": "W", "last_updated": "2026-08-21T07:00:00Z"
        },
        "sensor.inverter_load_power": {
            "state": "726", "unit": "W", "last_updated": "2026-08-21T07:00:00Z"
        },
        "sensor.inverter_battery_power": {
            "state": "-18", "unit": "W", "last_updated": "2026-08-21T07:00:00Z"
        },
        "sensor.inverter_pv_power": {
            "state": "0", "unit": "W", "last_updated": "2026-08-21T07:00:00Z"
        },
    }
    monkeypatch.setattr(
        project_tools,
        "_ssh",
        lambda command, timeout=30: {
            "ok": True,
            "returncode": 0,
            "stdout": json.dumps(states),
            "stderr": "",
        },
    )

    result = project_tools.energy_flow_health()

    assert result["healthy"] is True
    assert result["balance"]["grid_total_w"] == 1550
    assert result["balance"]["inverter_grid_branch_w"] == 803
    assert result["balance"]["outside_inverter_w"] == 747
    assert result["balance"]["balance_error_w"] == 0


def test_energy_flow_health_requires_deployed_templates(monkeypatch) -> None:
    states = {
        "sensor.zagalne_navantazhennia": {"state": "0.90", "unit": "kW"},
        "sensor.merezha_potuzhnist_usogo_vvodu": None,
        "sensor.inverter_grid_power": {"state": "810", "unit": "W"},
        "sensor.spozhivannia_poza_invertorom": None,
    }
    monkeypatch.setattr(
        project_tools,
        "_ssh",
        lambda command, timeout=30: {
            "ok": True,
            "returncode": 0,
            "stdout": json.dumps(states),
            "stderr": "",
        },
    )

    result = project_tools.energy_flow_health()

    assert result["healthy"] is False
    assert result["templates_ready"] is False
    assert result["balance"]["expected_outside_inverter_w"] == 90


def test_energy_flow_health_reports_missing_board_token(monkeypatch) -> None:
    monkeypatch.setattr(
        project_tools,
        "_ssh",
        lambda *_args, **_kwargs: {
            "ok": True,
            "returncode": 0,
            "stdout": json.dumps(
                {
                    "_error": "token_missing",
                    "token_file": "/home/forlinx/.ha_token",
                }
            ),
            "stderr": "",
        },
    )

    result = project_tools.energy_flow_health()

    assert result["healthy"] is False
    assert result["reason"] == "token_missing"
    assert result["sources"] == {}
