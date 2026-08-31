"""Read-only operational helpers for the HomeAssistant project MCP server."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(
    os.environ.get("HA_PROJECT_ROOT", Path(__file__).resolve().parents[1])
).resolve()
BOARD_HOST = os.environ.get("HA_BOARD_HOST", "forlinx@192.168.50.141")
SSH_KEY = Path(
    os.environ.get("HA_SSH_KEY", r"C:\SPB_Data\.ssh\mb35x8_ed25519")
).expanduser()
HA_VENV = os.environ.get("HA_VENV", "/userdata/hass/venv")
HA_CONFIG_ROOT = os.environ.get("HA_CONFIG_ROOT", "/userdata/hass/config")
HA_TOKEN_FILE = os.environ.get("HA_TOKEN_FILE", "/home/forlinx/.ha_token")

IRRIGATION_CONTROLLER_IP = "192.168.50.221"
IRRIGATION_CONTROLLER_MAC = "38:2c:e5:2d:5b:32"
IRRIGATION_PUMP_IP = "192.168.50.91"
LOCALTUYA_PORT = 6668
WELL_PUMP_IP = "192.168.50.26"
WELL_PUMP_MAC = "86:0f:3b:0a:36:91"
WELL_PUMP_DEVICE_ID = "bf45e77e78eac99afcpbgl"
WELL_PUMP_SCAN_INTERVAL_SECONDS = 1

SYNC_TARGETS: dict[str, str] = {
    "board-config/configuration.yaml": "/userdata/hass/config/configuration.yaml",
    "board-config/devices_dashboard.yaml": "/userdata/hass/config/devices_dashboard.yaml",
    "board-config/power_dashboard.yaml": "/userdata/hass/config/power_dashboard.yaml",
    "board-config/automations.yaml": "/userdata/hass/config/automations.yaml",
    "board-config/scripts.yaml": "/userdata/hass/config/scripts.yaml",
    "board-config/scenes.yaml": "/userdata/hass/config/scenes.yaml",
    "board-config/network_monitoring.yaml": "/userdata/hass/config/network_monitoring.yaml",
    # Кастомні картки. До 2026-08-30 їх тут не було, і вісім із дев'яти жили
    # лише на платі: правку картки води ніхто не бачив у git, а sync мовчав.
    "board-config/www/home-energy-flow-card.js": "/userdata/hass/config/www/home-energy-flow-card.js",
    "board-config/www/well-daily-water-card.js": "/userdata/hass/config/www/well-daily-water-card.js",
    "board-config/www/well-hourly-water-card.js": "/userdata/hass/config/www/well-hourly-water-card.js",
    "board-config/www/well-water-overview-card.js": "/userdata/hass/config/www/well-water-overview-card.js",
    "board-config/www/well-monthly-water-card.js": "/userdata/hass/config/www/well-monthly-water-card.js",
    "board-config/www/well-meter-entry-card.js": "/userdata/hass/config/www/well-meter-entry-card.js",
    "board-config/www/well-pump-runs-card.js": "/userdata/hass/config/www/well-pump-runs-card.js",
    "board-config/www/well-pump-log-card.js": "/userdata/hass/config/www/well-pump-log-card.js",
    "board-config/www/well-readings-log-card.js": "/userdata/hass/config/www/well-readings-log-card.js",
    # systemd. Три NFS-маунти свідомо не тут: їхні імена містять
    # systemd-екранування зі зворотним слешем
    # (userdata-hass-config\x2dstandalone-backups.mount), а такий символ
    # неприпустимий в імені файлу на Windows, де живе робоча копія.
    # Ними керує nas-mounts.service, який під контролем.
    "board-config/systemd/home-assistant.service": "/etc/systemd/system/home-assistant.service",
    "board-config/systemd/zram-swap.service": "/etc/systemd/system/zram-swap.service",
    "board-config/systemd/mnt-homemate_media-foto.mount": "/etc/systemd/system/mnt-homemate_media-foto.mount",
    "board-config/systemd/wyoming-vosk.service": "/etc/systemd/system/wyoming-vosk.service",
    "board-config/systemd/nas-mounts.service": "/etc/systemd/system/nas-mounts.service",
    "board-config/systemd/nas-mounts.timer": "/etc/systemd/system/nas-mounts.timer",
    "board-config/systemd/netplan-fallback.service": "/etc/systemd/system/netplan-fallback.service",
    "board-config/systemd/mirror-alias-ip.service": "/etc/systemd/system/mirror-alias-ip.service",
    # Ці два лишаються навмисно, хоч на платі їх немає: нічний аналіз дому
    # зник разом із ними, і remote_missing тут - потрібний сигнал, а не шум.
    "board-config/systemd/house-analyst.service": "/etc/systemd/system/house-analyst.service",
    "board-config/systemd/house-analyst.timer": "/etc/systemd/system/house-analyst.timer",
}


def _run(command: list[str], timeout: int = 30) -> dict[str, Any]:
    """Run a fixed command and return structured, bounded output."""
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-100_000:],
            "stderr": completed.stderr[-20_000:],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": str(exc)}


# Плата на eMMC відповідає повільно: серія sha256sum чи grep по журналу легко
# перевищує півхвилини, і всі health-інструменти поверталися таймаутом замість
# даних (спостережено 2026-08-10). Ліміт піднято до півтори хвилини.
def _ssh(remote_command: str, timeout: int = 90) -> dict[str, Any]:
    executable = "ssh.exe" if os.name == "nt" else "ssh"
    command = [
        executable,
        "-i",
        str(SSH_KEY),
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        BOARD_HOST,
        remote_command,
    ]
    return _run(command, timeout=timeout)


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_lf(path: Path) -> str | None:
    """Hash the file with CR removed, so CRLF and LF copies compare equal.

    На Windows робоча копія репозиторію тримає CRLF, а плата - LF, тому чотири
    systemd-юніти роками показувалися як mismatch, хоча текст у них однаковий
    (різниця рівно один байт на рядок). Постійний хибний mismatch знецінює саме
    те правило, заради якого ця звірка існує: розбіжність - це стоп-сигнал.
    """
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk.replace(b"\r", b""))
    return digest.hexdigest()


def resolve_targets(files: Iterable[str] | None = None) -> dict[str, str]:
    """Resolve only explicitly allow-listed repository paths."""
    if files is None:
        return dict(SYNC_TARGETS)
    selected: dict[str, str] = {}
    for raw in files:
        normalized = raw.replace("\\", "/").lstrip("./")
        if normalized not in SYNC_TARGETS:
            raise ValueError(
                f"Unsupported sync target {raw!r}; allowed: {', '.join(SYNC_TARGETS)}"
            )
        selected[normalized] = SYNC_TARGETS[normalized]
    return selected


def repo_board_sync(files: Iterable[str] | None = None) -> dict[str, Any]:
    """Compare SHA-256 hashes without copying or changing either side."""
    targets = resolve_targets(files)
    remote_paths = list(targets.values())
    # Шляхи перелічуються один раз і обходяться циклом. Раніше кожен шлях
    # підставлявся в команду чотири рази, і на 26 таргетах рядок переріс ліміт
    # аргументів: ssh діставав обрізаний скрипт, bash відповідав
    # "syntax error: unexpected end of file", а sync позначав УСІ файли як
    # remote_error - тобто виглядав як недоступна плата (2026-08-31).
    #
    # Другий, LFHASH-рядок - той самий файл без CR. Дає змогу відрізнити
    # реальну розбіжність від різниці переносів рядків Windows і плати.
    quoted_paths = ' '.join(shlex.quote(path) for path in remote_paths)
    script = (
        f"for p in {quoted_paths}; do "
        'if [ -f "$p" ]; then sha256sum "$p"; '
        'printf %s "LFHASH $p "; '
        'tr -d "\\r" < "$p" | sha256sum | cut -c1-64; '
        'else printf "MISSING  %s\\n" "$p"; fi; '
        'done'
    )
    remote = _ssh(script, timeout=150)
    remote_hashes: dict[str, str | None] = {}
    remote_lf_hashes: dict[str, str] = {}
    if remote["ok"]:
        for line in remote["stdout"].splitlines():
            if line.startswith("MISSING  "):
                remote_hashes[line[9:].strip()] = None
                continue
            if line.startswith("LFHASH "):
                body = line[7:].strip()
                path_part, _, hash_part = body.rpartition(" ")
                if re.fullmatch(r"[0-9a-fA-F]{64}", hash_part):
                    remote_lf_hashes[path_part.strip()] = hash_part.lower()
                continue
            match = re.match(r"^([0-9a-fA-F]{64})\s+(.+)$", line)
            if match:
                remote_hashes[match.group(2).strip()] = match.group(1).lower()

    results = []
    for repo_path, remote_path in targets.items():
        local_hash = _sha256(PROJECT_ROOT / repo_path)
        remote_hash = remote_hashes.get(remote_path)
        if not remote["ok"]:
            status = "remote_error"
        elif local_hash is None:
            status = "local_missing"
        elif remote_hash is None:
            status = "remote_missing"
        elif local_hash == remote_hash:
            status = "match"
        elif (
            remote_lf_hashes.get(remote_path) is not None
            and _sha256_lf(PROJECT_ROOT / repo_path) == remote_lf_hashes[remote_path]
        ):
            # Текст однаковий, різняться лише переноси рядків. Це не привід
            # зупиняти деплой, але й не мовчазний match - хай буде видно.
            status = "match_eol_only"
        else:
            status = "mismatch"
        results.append(
            {
                "repo_path": repo_path,
                "board_path": remote_path,
                "local_sha256": local_hash,
                "board_sha256": remote_hash,
                "status": status,
            }
        )
    return {
        "safe_to_deploy": bool(results)
        and remote["ok"]
        and all(
            item["status"] in ("match", "match_eol_only") for item in results
        ),
        "results": results,
        "remote_error": remote["stderr"] if not remote["ok"] else "",
    }


def board_health() -> dict[str, Any]:
    """Read the board, HA, storage, swap, journal cap, and timer health."""
    command = f"""
printf 'ha_version='; {shlex.quote(HA_VENV)}/bin/hass --version 2>/dev/null || true
printf 'ha_service='; systemctl is-active home-assistant 2>/dev/null || true
printf 'ha_http='; curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 http://localhost:8123/ || true; printf '\n'
printf 'uptime='; uptime -p 2>/dev/null || true
printf 'journal_cap='; grep -E '^SystemMaxUse=' /etc/systemd/journald.conf 2>/dev/null | tail -n1 | cut -d= -f2
printf 'root='; df -P / 2>/dev/null | tail -n1
printf 'userdata='; df -P /userdata 2>/dev/null | tail -n1
printf 'swap='; swapon --show --noheadings 2>/dev/null | tr '\n' ';'; printf '\n'
printf 'nas_timer='; systemctl is-enabled homemate-nas-sync.timer 2>/dev/null || true
printf 'ha_backup_timer='; systemctl is-enabled homemate-ha-backups-mount.timer 2>/dev/null || true
printf 'ha_backup_mount='; systemctl is-active userdata-hass-config-backups.mount 2>/dev/null || true
printf 'photo_mount='; systemctl is-active mnt-homemate_media-foto.mount 2>/dev/null || true
printf 'analyst_timer='; systemctl is-enabled house-analyst.timer 2>/dev/null || true
""".strip()
    result = _ssh(command, timeout=120)
    values: dict[str, str] = {}
    for line in result["stdout"].splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    healthy = (
        result["ok"]
        and values.get("ha_service") == "active"
        and values.get("ha_http") == "200"
    )
    return {"healthy": healthy, "values": values, "transport": result}


def irrigation_health() -> dict[str, Any]:
    """Check LocalTuya transport readiness without operating pump or valves.

    Readiness here is about transport only. Never infer a fault from the pump
    running while every valve is closed: the property has garden hydrants for a
    hose, the pump is started freely from the physical button or the interface,
    and that is an ordinary event rather than dry running.
    See ``.claude/skills/home-assistant/references/irrigation.md``.
    """
    command = f"""
printf 'ha_service='; systemctl is-active home-assistant 2>/dev/null || true
printf 'ha_http='; curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 http://localhost:8123/ || true; printf '\n'
if ping -c 1 -W 1 {IRRIGATION_CONTROLLER_IP} >/dev/null 2>&1; then echo 'controller_ping=ok'; else echo 'controller_ping=failed'; fi
printf 'controller_neighbor='; ip neigh show {IRRIGATION_CONTROLLER_IP} 2>/dev/null | head -n1
if sudo ss -Hntp 2>/dev/null | grep -F '{IRRIGATION_CONTROLLER_IP}:{LOCALTUYA_PORT}' | grep -Fq 'hass'; then echo 'controller_localtuya=established'; else echo 'controller_localtuya=disconnected'; fi
if ping -c 1 -W 1 {IRRIGATION_PUMP_IP} >/dev/null 2>&1; then echo 'pump_ping=ok'; else echo 'pump_ping=failed'; fi
printf 'pump_neighbor='; ip neigh show {IRRIGATION_PUMP_IP} 2>/dev/null | head -n1
if sudo ss -Hntp 2>/dev/null | grep -F '{IRRIGATION_PUMP_IP}:{LOCALTUYA_PORT}' | grep -Fq 'hass'; then echo 'pump_localtuya=established'; else echo 'pump_localtuya=disconnected'; fi
printf 'controller_errors_10m='; sudo journalctl -u home-assistant --since '-10 min' --no-pager 2>/dev/null | grep -iE 'bf9.*dy4|192\\.168\\.50\\.221|avtopoliv_kontroler' | grep -ciE 'failed|not connected|unavailable|does not match' || true
printf 'pump_errors_10m='; sudo journalctl -u home-assistant --since '-10 min' --no-pager 2>/dev/null | grep -iE '192\\.168\\.50\\.91|mini_switch_k601' | grep -ciE 'failed|not connected|unavailable|does not match' || true
""".strip()
    result = _ssh(command, timeout=120)
    values: dict[str, str] = {}
    for line in result["stdout"].splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()

    neighbor = values.get("controller_neighbor", "").casefold()
    controller_mac_ok = (
        IRRIGATION_CONTROLLER_MAC in neighbor
        and "failed" not in neighbor
        and "incomplete" not in neighbor
    )
    controller_ready = (
        result["ok"]
        and values.get("ha_service") == "active"
        and values.get("ha_http") == "200"
        and values.get("controller_ping") == "ok"
        and controller_mac_ok
        and values.get("controller_localtuya") == "established"
        and values.get("controller_errors_10m") == "0"
    )
    irrigation_ready = (
        controller_ready
        and values.get("pump_ping") == "ok"
        and values.get("pump_localtuya") == "established"
        and values.get("pump_errors_10m") == "0"
    )
    return {
        "controller_ready": controller_ready,
        "irrigation_ready": irrigation_ready,
        "control_path": "LocalTuya over LAN TCP/6668; cloud Tuya is not the execution path",
        "values": values,
        "criteria": {
            "controller": "HA active/HTTP 200, expected IP/MAC reachable, hass TCP/6668 established, no matching errors for 10 minutes",
            "full_irrigation": "controller ready plus pump relay reachable with hass TCP/6668 established and no matching errors for 10 minutes",
            "physical_proof": "A controlled valve command must still report the selected LocalTuya switch on within 8 seconds; this read-only check never moves hardware",
            "pump_without_valve": "Never an emergency: garden hydrants let the pump feed a hose with every valve closed, and manual start has no conditions at all. Only the three-hour maximum runtime limits it",
        },
        "transport": result,
    }


def well_pump_health() -> dict[str, Any]:
    """Check the well-pump LocalTuya transport without operating the pump.

    This intentionally avoids Home Assistant storage and device credentials.
    A healthy TCP session proves the local control path is connected, not that
    the pump is running or that Recorder writes one row per polling interval.
    """
    command = rf"""
printf 'ha_service='; systemctl is-active home-assistant 2>/dev/null || true
printf 'ha_http='; curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 http://localhost:8123/ || true; printf '\n'
if ping -c 1 -W 1 {WELL_PUMP_IP} >/dev/null 2>&1; then echo 'well_pump_ping=ok'; else echo 'well_pump_ping=failed'; fi
printf 'well_pump_neighbor='; ip neigh show {WELL_PUMP_IP} 2>/dev/null | head -n1
if sudo ss -Hntp 2>/dev/null | grep -F '{WELL_PUMP_IP}:{LOCALTUYA_PORT}' | grep -Fq 'hass'; then echo 'well_pump_localtuya=established'; else echo 'well_pump_localtuya=disconnected'; fi
printf 'well_pump_errors_10m='; sudo journalctl -u home-assistant --since '-10 min' --no-pager 2>/dev/null | grep -iE '{WELL_PUMP_DEVICE_ID}|192\.168\.50\.26|t34_smart_plug' | grep -ciE 'failed|not connected|unavailable|does not match|exception' || true
""".strip()
    result = _ssh(command, timeout=120)
    values: dict[str, str] = {}
    for line in result["stdout"].splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()

    neighbor = values.get("well_pump_neighbor", "").casefold()
    mac_ok = (
        WELL_PUMP_MAC in neighbor
        and "failed" not in neighbor
        and "incomplete" not in neighbor
    )
    ready = (
        result["ok"]
        and values.get("ha_service") == "active"
        and values.get("ha_http") == "200"
        and values.get("well_pump_ping") == "ok"
        and mac_ok
        and values.get("well_pump_localtuya") == "established"
        and values.get("well_pump_errors_10m") == "0"
    )
    return {
        "well_pump_ready": ready,
        "control_path": (
            "LocalTuya 3.5 relay over LAN TCP/6668; cloud power telemetry "
            "fallback while LocalTuya power_2 remains zero"
        ),
        "expected_scan_interval_seconds": WELL_PUMP_SCAN_INTERVAL_SECONDS,
        "values": values,
        "entities": {
            "switch": "switch.t34_smart_plug_switch_1_2",
            "power": "sensor.t34_smart_plug_power",
            "power_local": "sensor.t34_smart_plug_power_2",
            "current": "sensor.t34_smart_plug_current_2",
            "voltage": "sensor.t34_smart_plug_voltage_2",
            "integrated_energy": (
                "sensor.t34_smart_plug_nasos_sverdlovini_spozhito"
            ),
        },
        "criteria": {
            "transport": (
                "HA active/HTTP 200, expected IP/MAC reachable, hass TCP/6668 "
                "established, and no matching errors for 10 minutes"
            ),
            "cadence": (
                "LocalTuya is configured for a 1-second scan, but power_2 is "
                "currently diagnostic-only because it has not produced a "
                "non-zero sample. Operational dashboards use cloud power until "
                "a natural run proves local telemetry"
            ),
            "physical_proof": (
                "Observe the next natural pump run unless the owner explicitly "
                "authorizes actuation; this tool never switches the pump"
            ),
            "storage_boundary": (
                "The scan interval and local key live in Home Assistant storage; "
                "this read-only tool never reads or returns them"
            ),
        },
        "transport": result,
    }


def energy_flow_health() -> dict[str, Any]:
    """Read the whole-site/inverter power split without changing HA.

    The three-phase inlet meter is upstream of Deye. Therefore the Deye grid
    sensor is only one branch of the site and must never be presented as total
    grid demand. The remote helper reads a small allow-list through HA's local
    API; the access token is consumed on the board and is never returned.
    """
    entity_ids = (
        "sensor.zagalne_navantazhennia",
        "sensor.merezha_potuzhnist_usogo_vvodu",
        "sensor.inverter_grid_power",
        "sensor.spozhivannia_poza_invertorom",
        "sensor.inverter_load_power",
        "sensor.inverter_battery_power",
        "sensor.inverter_pv_power",
    )
    remote_script = f"""
import json
import os
import urllib.request

ids = {entity_ids!r}
token_path = {HA_TOKEN_FILE!r}
if not os.path.isfile(token_path):
    print(json.dumps({{'_error': 'token_missing', 'token_file': token_path}}))
    raise SystemExit(0)
token = open(token_path, encoding='utf-8').read().strip()
request = urllib.request.Request(
    'http://localhost:8123/api/states',
    headers={{'Authorization': 'Bearer ' + token}},
)
with urllib.request.urlopen(request, timeout=10) as response:
    states = {{item['entity_id']: item for item in json.load(response)}}
result = {{}}
for entity_id in ids:
    item = states.get(entity_id)
    result[entity_id] = None if item is None else {{
        'state': item.get('state'),
        'unit': item.get('attributes', {{}}).get('unit_of_measurement'),
        'last_updated': item.get('last_updated'),
    }}
print(json.dumps(result, ensure_ascii=False))
""".strip()
    command = (
        f"{shlex.quote(HA_VENV)}/bin/python -c "
        + shlex.quote(remote_script)
    )
    transport = _ssh(command, timeout=60)
    if not transport["ok"]:
        return {
            "healthy": False,
            "reason": "transport_error",
            "sources": {},
            "transport": transport,
        }

    try:
        states = json.loads(transport["stdout"])
    except json.JSONDecodeError:
        return {
            "healthy": False,
            "reason": "invalid_home_assistant_response",
            "sources": {},
            "transport": transport,
        }

    if states.get("_error"):
        return {
            "healthy": False,
            "reason": states["_error"],
            "token_file": states.get("token_file"),
            "sources": {},
            "transport": transport,
        }

    def number(entity_id: str) -> float | None:
        item = states.get(entity_id)
        if not isinstance(item, dict):
            return None
        raw = item.get("state")
        if raw in (None, "unknown", "unavailable"):
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    total_kw = number("sensor.zagalne_navantazhennia")
    total_w = number("sensor.merezha_potuzhnist_usogo_vvodu")
    inverter_grid_w = number("sensor.inverter_grid_power")
    outside_w = number("sensor.spozhivannia_poza_invertorom")
    expected_outside_w = (
        max(total_kw * 1000 - inverter_grid_w, 0)
        if total_kw is not None and inverter_grid_w is not None
        else None
    )
    balance_error_w = (
        outside_w - expected_outside_w
        if outside_w is not None and expected_outside_w is not None
        else None
    )
    templates_ready = total_w is not None and outside_w is not None
    healthy = (
        total_kw is not None
        and inverter_grid_w is not None
        and templates_ready
        and balance_error_w is not None
        and abs(balance_error_w) <= 5
    )
    return {
        "healthy": healthy,
        "topology": (
            "grid inlet = inverter grid branch + consumption outside inverter; "
            "inverter then splits to protected load, battery and PV"
        ),
        "sources": states,
        "balance": {
            "grid_total_w": total_w if total_w is not None else (
                total_kw * 1000 if total_kw is not None else None
            ),
            "inverter_grid_branch_w": inverter_grid_w,
            "outside_inverter_w": outside_w,
            "expected_outside_inverter_w": expected_outside_w,
            "balance_error_w": balance_error_w,
            "inverter_load_w": number("sensor.inverter_load_power"),
            "battery_w": number("sensor.inverter_battery_power"),
            "pv_w": number("sensor.inverter_pv_power"),
        },
        "templates_ready": templates_ready,
        "criteria": {
            "source": "whole-site total comes from the upstream three-phase meter",
            "split": "outside inverter = whole-site grid power - Deye grid branch",
            "tolerance_w": 5,
            "dashboard": (
                "Sunsynk full card maps grid_ct_power_172 to whole-site power, "
                "grid_power_169 to Deye and nonessential_power to the difference"
            ),
        },
        "transport": transport,
    }


def validate_config() -> dict[str, Any]:
    """Run the official HA config checker without restarting the service."""
    command = (
        f"{shlex.quote(HA_VENV)}/bin/hass --script check_config "
        f"-c {shlex.quote(HA_CONFIG_ROOT)}"
    )
    return _ssh(command, timeout=180)


def recent_logs(lines: int = 100, pattern: str | None = None) -> dict[str, Any]:
    """Read recent HA journald output and optionally filter it locally."""
    lines = max(1, min(int(lines), 1000))
    result = _ssh(
        f"sudo journalctl -u home-assistant -n {lines} --no-pager",
        timeout=30,
    )
    if pattern and result["ok"]:
        if len(pattern) > 200:
            raise ValueError("pattern is limited to 200 characters")
        regex = re.compile(pattern, re.IGNORECASE)
        result["stdout"] = "\n".join(
            line for line in result["stdout"].splitlines() if regex.search(line)
        )
    return result


def git_status() -> dict[str, Any]:
    """Return repository status without fetching or modifying refs."""
    status = _run(["git", "status", "--short", "--branch"])
    branch = _run(["git", "branch", "--show-current"])
    upstream = _run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    divergence: dict[str, Any] | None = None
    if upstream["ok"]:
        counts = _run(["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"])
        if counts["ok"]:
            parts = counts["stdout"].strip().split()
            if len(parts) == 2:
                divergence = {"ahead": int(parts[0]), "behind": int(parts[1])}
    return {
        "branch": branch["stdout"].strip(),
        "upstream": upstream["stdout"].strip() if upstream["ok"] else None,
        "divergence": divergence,
        "status": status,
    }


INCIDENTS_PATH = (
    "/userdata/hass/config/.private/claude-code-conversation/incidents.jsonl"
)


def incidents(status: str = "open") -> dict[str, Any]:
    """Read the board's incident register. Read-only, never writes.

    Реєстр веде асистент і оператор через чат; тут він потрібен, щоб
    обслуговча сесія бачила той самий перелік відкритих проблем, що й агент,
    і не починала розбір з нуля.
    """
    result = _ssh(f"cat {shlex.quote(INCIDENTS_PATH)} 2>/dev/null || true")
    if not result["ok"]:
        return {"ok": False, "count": 0, "incidents": [], "transport": result}
    wanted = status.strip().casefold()
    parsed: list[dict[str, Any]] = []
    for line in result["stdout"].splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        record_status = str(record.get("status", "open"))
        if wanted == "all":
            parsed.append(record)
        elif wanted == "open":
            if record_status in ("open", "watching"):
                parsed.append(record)
        elif record_status == wanted:
            parsed.append(record)
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    parsed.sort(
        key=lambda item: (
            severity_rank.get(str(item.get("severity")), 3),
            str(item.get("updated", "")),
        )
    )
    return {"ok": True, "filter": wanted, "count": len(parsed), "incidents": parsed}


def network_inventory(query: str | None = None) -> dict[str, Any]:
    """Read the versioned fixed-device inventory; optionally match IP/MAC/name."""
    path = Path(__file__).with_name("network_inventory.json")
    devices = json.loads(path.read_text(encoding="utf-8"))["devices"]
    if query:
        needle = query.casefold().replace("-", ":")
        devices = [
            device
            for device in devices
            if needle
            in " ".join(str(value) for value in device.values())
            .casefold()
            .replace("-", ":")
        ]
    return {"count": len(devices), "devices": devices}


def project_summary() -> dict[str, Any]:
    return {
        "project_root": str(PROJECT_ROOT),
        "board": BOARD_HOST,
        "ssh_key": str(SSH_KEY),
        "home_assistant_url": "http://192.168.50.141:8123/",
        "config_root": HA_CONFIG_ROOT,
        "venv": HA_VENV,
        "protected": [".storage", "secrets.yaml", "*.db", "tokens", "credentials"],
        "sync_targets": SYNC_TARGETS,
    }
