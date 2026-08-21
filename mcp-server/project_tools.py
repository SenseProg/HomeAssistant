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
    "board-config/systemd/home-assistant.service": "/etc/systemd/system/home-assistant.service",
    "board-config/systemd/zram-swap.service": "/etc/systemd/system/zram-swap.service",
    "board-config/systemd/homemate-nas-sync.service": "/etc/systemd/system/homemate-nas-sync.service",
    "board-config/systemd/homemate-nas-sync.timer": "/etc/systemd/system/homemate-nas-sync.timer",
    "board-config/systemd/userdata-hass-config-backups.mount": "/etc/systemd/system/userdata-hass-config-backups.mount",
    "board-config/systemd/homemate-ha-backups-mount.timer": "/etc/systemd/system/homemate-ha-backups-mount.timer",
    "board-config/systemd/mnt-homemate_media-foto.mount": "/etc/systemd/system/mnt-homemate_media-foto.mount",
    "board-config/systemd/house-analyst.service": "/etc/systemd/system/house-analyst.service",
    "board-config/systemd/house-analyst.timer": "/etc/systemd/system/house-analyst.timer",
    "board-config/systemd/wyoming-vosk.service": "/etc/systemd/system/wyoming-vosk.service",
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
    script_parts = []
    for remote_path in remote_paths:
        quoted = shlex.quote(remote_path)
        # Другий, LFHASH-рядок - той самий файл без CR. Дає змогу відрізнити
        # реальну розбіжність від різниці переносів рядків Windows і плати.
        script_parts.append(
            f"if [ -f {quoted} ]; then sha256sum {quoted}; "
            f"printf 'LFHASH %s ' {quoted}; "
            f"tr -d '\\r' < {quoted} | sha256sum | cut -c1-64; "
            f"else printf 'MISSING  %s\\n' {quoted}; fi"
        )
    remote = _ssh("; ".join(script_parts), timeout=150)
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
    command = """
printf 'ha_version='; /home/forlinx/hass-venv-314/bin/hass --version 2>/dev/null || true
printf 'ha_service='; systemctl is-active home-assistant 2>/dev/null || true
printf 'ha_http='; curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:8123/ || true; printf '\n'
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
        "control_path": "LocalTuya 3.5 over LAN TCP/6668",
        "expected_scan_interval_seconds": WELL_PUMP_SCAN_INTERVAL_SECONDS,
        "values": values,
        "entities": {
            "switch": "switch.t34_smart_plug_switch_1_2",
            "power": "sensor.t34_smart_plug_power_2",
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
                "The live LocalTuya device is configured for a 1-second scan. "
                "Recorder stores changed states, so an unchanged value does not "
                "produce one history row per second"
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


def validate_config() -> dict[str, Any]:
    """Run the official HA config checker without restarting the service."""
    command = (
        "/home/forlinx/hass-venv-314/bin/hass --script check_config "
        "-c /userdata/hass/config"
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
        "config_root": "/userdata/hass/config",
        "protected": [".storage", "secrets.yaml", "*.db", "tokens", "credentials"],
        "sync_targets": SYNC_TARGETS,
    }
