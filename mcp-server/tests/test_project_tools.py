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
    assert result["count"] == 23
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


def _configuration_yaml_text() -> str:
    path = Path(__file__).resolve().parents[2] / "board-config" / "configuration.yaml"
    return path.read_text(encoding="utf-8")


def test_sync_targets_cover_registered_dashboards() -> None:
    """Кожен YAML-дашборд із lovelace.dashboards має звірятися з платою.

    Аудит 22.08.2026 казав, що overview_dashboard.yaml додано, а в main його не
    було - головна сторінка жила поза sync. Цей тест не дасть такому повторитись.
    """
    import re

    filenames = re.findall(r"^\s+filename:\s+(\S+\.yaml)", _configuration_yaml_text(), re.M)
    assert filenames, "lovelace.dashboards has no filename entries?"
    for name in filenames:
        assert f"board-config/{name}" in project_tools.SYNC_TARGETS, name


def test_sync_targets_cover_config_scripts() -> None:
    """Скрипти, які викликає command_line/shell_command, мусять бути в Git і в sync."""
    import re

    scripts = set(
        re.findall(r"/userdata/hass/config/scripts/([A-Za-z0-9_-]+\.py)", _configuration_yaml_text())
    )
    assert scripts, "configuration.yaml references no scripts?"
    repo_root = Path(__file__).resolve().parents[2]
    for name in sorted(scripts):
        repo_path = f"board-config/scripts/{name}"
        assert repo_path in project_tools.SYNC_TARGETS, name
        assert (repo_root / repo_path).is_file(), repo_path


HEALTHY_STDOUT = """ha_version=2026.7.4
ha_service=active
ha_http=200
uptime=up 2 hours
journal_cap=50M
root=/dev/root 12320264 9609344 2142472 82% /
userdata=/dev/mmcblk0p8 2525760 1530660 891772 64% /userdata
root_free_mb=2094
userdata_free_mb=872
mem_available_mb=1014
swap_used_mb=0
swap=/dev/zram0 partition 1024M 0B 100;
fs_state=clean
fs_error_count=0
fs_journal=1
backup_mount_nfs=1
backup_newest=/userdata/hass/config/backups/Automatic_backup_x.tar
backup_age_h=12
backup_size_mb=48
photo_mount=active
nas_mounts_timer=enabled
analyst_timer=missing
cloudflared=active
tailscale=running
inverter_ping=ok
well_pump_ping=ok
entities_total=983
entities_unavailable=40
inverter_unavailable=0
automations_orphaned=0
"""


def _ssh_stub(stdout: str):
    return lambda command, timeout=30: {
        "ok": True,
        "returncode": 0,
        "stdout": stdout,
        "stderr": "",
    }


def test_board_health_is_healthy_only_when_everything_passes(monkeypatch) -> None:
    monkeypatch.setattr(project_tools, "_ssh", _ssh_stub(HEALTHY_STDOUT))
    result = project_tools.board_health()
    assert result["healthy"] is True
    assert result["problems"] == []
    assert result["values"]["nas_mounts_timer"] == "enabled"


def test_board_health_reports_filesystem_backup_and_link_problems(monkeypatch) -> None:
    """Стан 02.09.2026: ФС з помилками і без журналу, бекап 7 ГБ, Tailscale
    розлогінений, інвертор і насос свердловини не пінгуються, 18 привидів.
    Стара версія на цьому казала healthy=true."""
    sick = (
        HEALTHY_STDOUT.replace("fs_state=clean", "fs_state=not clean with errors")
        .replace("fs_error_count=0", "fs_error_count=9")
        .replace("fs_journal=1", "fs_journal=0")
        .replace("backup_size_mb=48", "backup_size_mb=6896")
        .replace("tailscale=running", "tailscale=logged_out")
        .replace("inverter_ping=ok", "inverter_ping=failed")
        .replace("well_pump_ping=ok", "well_pump_ping=failed")
        .replace("automations_orphaned=0", "automations_orphaned=18")
    )
    monkeypatch.setattr(project_tools, "_ssh", _ssh_stub(sick))
    result = project_tools.board_health()
    assert result["healthy"] is False
    joined = " | ".join(result["problems"])
    for needle in ("filesystem has errors", "no journal", "dragging NAS media",
                   "tailscale is logged out", "Deye logger", "well pump plug", "18 automation"):
        assert needle in joined, needle
    # Ключі більше не клеяться: кожне поле окремо.
    assert result["values"]["cloudflared"] == "active"
    assert result["values"]["analyst_timer"] == "missing"


def test_storage_dashboards_sync_matches_when_board_equals_repo(monkeypatch) -> None:
    """Живий конфіг storage-дашборда (через lovelace_push --dump) звіряється з файлом."""
    import yaml

    repo_root = Path(__file__).resolve().parents[2]

    def fake_ssh(command, timeout=30):
        url_path = command.split(" - ")[1].split(" ")[0]
        repo_path = next(p for p, u in project_tools.STORAGE_DASHBOARDS.items() if u == url_path)
        doc = yaml.safe_load((repo_root / repo_path).read_text(encoding="utf-8"))
        cfg = {k: v for k, v in doc.items() if k != "title"}
        if url_path == "sverdlovina-dashboard":
            cfg["views"][0]["badges"] = []  # хтось прибрав бейджі в UI
        return {"ok": True, "returncode": 0, "stdout": json.dumps(cfg, ensure_ascii=False), "stderr": ""}

    monkeypatch.setattr(project_tools, "_ssh", fake_ssh)
    result = project_tools.storage_dashboards_sync()
    by_path = {r["url_path"]: r["status"] for r in result["results"]}
    assert by_path["spovishchennia-zhurnal"] == "match"
    assert by_path["sverdlovina-dashboard"] == "mismatch"
    assert result["safe_to_push"] is False


def test_entity_states_validates_pattern() -> None:
    with pytest.raises(ValueError):
        project_tools.entity_states("")
    with pytest.raises(ValueError):
        project_tools.entity_states("x" * 201)


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
