"""Read-only operational helpers for the HomeAssistant project MCP server."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import time
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
    # Головна сторінка і заставка ТВ. Аудит 22.08 казав, що overview додано;
    # у main цього не було, і головна сторінка знову жила поза звіркою
    # (виявлено 02.09.2026). Тест test_sync_targets_cover_registered_dashboards
    # більше не дасть цьому повторитись.
    "board-config/overview_dashboard.yaml": "/userdata/hass/config/overview_dashboard.yaml",
    "board-config/tv_dashboard.yaml": "/userdata/hass/config/tv_dashboard.yaml",
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
    # Скрипти, на які configuration.yaml посилається з command_line і
    # shell_command. До 02.09.2026 жили лише на платі: відбудова з Git дала б
    # конфіг із посиланнями на неіснуючі файли, а sync мовчав би.
    # Тест test_sync_targets_cover_config_scripts стежить за повнотою.
    "board-config/scripts/notify_log.py": "/userdata/hass/config/scripts/notify_log.py",
    "board-config/scripts/water_readings.py": "/userdata/hass/config/scripts/water_readings.py",
    "board-config/scripts/tariffs.py": "/userdata/hass/config/scripts/tariffs.py",
    "board-config/scripts/lts_depth.py": "/userdata/hass/config/scripts/lts_depth.py",
    "board-config/scripts/minute_rollup.py": "/userdata/hass/config/scripts/minute_rollup.py",
    "board-config/scripts/backup_statistics.py": "/userdata/hass/config/scripts/backup_statistics.py",
    "board-config/scripts/flaky_devices.py": "/userdata/hass/config/scripts/flaky_devices.py",
    "board-config/scripts/lovelace_push.py": "/userdata/hass/config/scripts/lovelace_push.py",
    # Storage-дашборд журналу сповіщень: джерело правди - файл, на плату він
    # їде через lovelace_push.py, а не через lovelace.dashboards (рестарт).
    "board-config/notifications_dashboard.yaml": "/userdata/hass/config/notifications_dashboard.yaml",
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
    # Keepalive (аудит 22.08, зроблено 02.09): завислий канал без нього живе до
    # повного таймауту інструмента, а три такі виклики поспіль виглядають як
    # «плата недоступна» при живому SSH. Плюс elapsed_ms у відповіді - щоб
    # повільну плату було видно як повільну, а не як мертву.
    executable = "ssh.exe" if os.name == "nt" else "ssh"
    command = [
        executable,
        "-i",
        str(SSH_KEY),
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "ServerAliveInterval=10",
        "-o",
        "ServerAliveCountMax=3",
        BOARD_HOST,
        remote_command,
    ]
    started = time.monotonic()
    result = _run(command, timeout=timeout)
    result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    return result


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


BOARD_HEALTH_COMMAND = f"""
v=$({shlex.quote(HA_VENV)}/bin/hass --version 2>/dev/null || echo unknown); echo "ha_version=$v"
v=$(systemctl is-active home-assistant 2>/dev/null || echo inactive); echo "ha_service=$v"
v=$(curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 http://localhost:8123/ || echo 000); echo "ha_http=$v"
v=$(uptime -p 2>/dev/null || echo unknown); echo "uptime=$v"
v=$(grep -E '^SystemMaxUse=' /etc/systemd/journald.conf 2>/dev/null | tail -n1 | cut -d= -f2); echo "journal_cap=$v"
echo "root=$(df -P / 2>/dev/null | tail -n1)"
echo "userdata=$(df -P /userdata 2>/dev/null | tail -n1)"
echo "root_free_mb=$(df -Pm / 2>/dev/null | awk 'NR==2{{print $4}}')"
echo "userdata_free_mb=$(df -Pm /userdata 2>/dev/null | awk 'NR==2{{print $4}}')"
echo "mem_available_mb=$(free -m 2>/dev/null | awk '/^Mem:/{{print $7}}')"
echo "swap_used_mb=$(free -m 2>/dev/null | awk '/^Swap:/{{print $3}}')"
v=$(swapon --show --noheadings 2>/dev/null | tr '\\n' ';'); echo "swap=$v"
v=$(sudo dumpe2fs -h /dev/mmcblk0p8 2>/dev/null | awk -F': *' '/^Filesystem state/{{print $2}}'); echo "fs_state=$v"
v=$(sudo dumpe2fs -h /dev/mmcblk0p8 2>/dev/null | awk -F': *' '/^FS Error count/{{print $2}}'); echo "fs_error_count=${{v:-0}}"
v=$(sudo dumpe2fs -h /dev/mmcblk0p8 2>/dev/null | grep -c has_journal); echo "fs_journal=$v"
v=$(findmnt -n -o SOURCE -T /userdata/hass/config-standalone/backups 2>/dev/null | grep -c ':'); echo "backup_mount_nfs=$v"
f=$(ls -t /userdata/hass/config/backups/*.tar 2>/dev/null | head -n1); echo "backup_newest=$f"
if [ -n "$f" ]; then echo "backup_age_h=$(( ( $(date +%s) - $(stat -c %Y "$f") ) / 3600 ))"; echo "backup_size_mb=$(( $(stat -c %s "$f") / 1048576 ))"; else echo "backup_age_h="; echo "backup_size_mb="; fi
v=$(systemctl is-active mnt-homemate_media-foto.mount 2>/dev/null || echo inactive); echo "photo_mount=$v"
v=$(systemctl is-enabled nas-mounts.timer 2>/dev/null || echo missing); echo "nas_mounts_timer=$v"
v=$(systemctl is-enabled house-analyst.timer 2>/dev/null || echo missing); echo "analyst_timer=$v"
v=$(systemctl is-active cloudflared-ha 2>/dev/null || echo inactive); echo "cloudflared=$v"
if sudo tailscale status 2>&1 | grep -qi 'logged out'; then echo "tailscale=logged_out"; else echo "tailscale=running"; fi
if ping -c 1 -W 1 192.168.50.179 >/dev/null 2>&1; then echo "inverter_ping=ok"; else echo "inverter_ping=failed"; fi
if ping -c 1 -W 1 {WELL_PUMP_IP} >/dev/null 2>&1; then echo "well_pump_ping=ok"; else echo "well_pump_ping=failed"; fi
if [ -f {shlex.quote(HA_TOKEN_FILE)} ]; then
  {shlex.quote(HA_VENV)}/bin/python - <<'PYEOF'
import json, urllib.request
token = open({HA_TOKEN_FILE!r}, encoding='utf-8').read().strip()
req = urllib.request.Request('http://localhost:8123/api/states', headers={{'Authorization': 'Bearer ' + token}})
try:
    states = json.load(urllib.request.urlopen(req, timeout=15))
except Exception as exc:
    print('states_error=' + type(exc).__name__)
else:
    bad = [s for s in states if s['state'] in ('unavailable', 'unknown')]
    print('entities_total=%d' % len(states))
    print('entities_unavailable=%d' % len(bad))
    print('inverter_unavailable=%d' % sum(1 for s in bad if s['entity_id'].split('.', 1)[1].startswith('inverter_')))
    print('automations_orphaned=%d' % sum(1 for s in bad if s['entity_id'].startswith(('automation.', 'script.'))))
PYEOF
else
  echo "states_error=token_missing"
fi
""".strip()


def _parse_key_values(stdout: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def _int_or_none(raw: str | None) -> int | None:
    try:
        return int(raw) if raw not in (None, "") else None
    except ValueError:
        return None


def board_health() -> dict[str, Any]:
    """Read board, HA, storage, filesystem, backup, remote-access and link health.

    Переписано 02.09.2026. Стара версія казала healthy=true при файловій
    системі з помилками, розлогіненому Tailscale і офлайн-інверторі, а три
    ключі склеювала в один рядок, бо `systemctl is-enabled` неіснуючого юніта
    не друкує переносу. Тепер кожна перевірка - окреме поле, `problems` - їх
    людський перелік, а `healthy` істинне лише коли перелік порожній.
    """
    result = _ssh(BOARD_HEALTH_COMMAND, timeout=120)
    values = _parse_key_values(result["stdout"])
    problems: list[str] = []
    if not result["ok"]:
        problems.append("ssh transport failed")
    if values.get("ha_service") != "active":
        problems.append(f"home-assistant.service is {values.get('ha_service')}")
    if values.get("ha_http") != "200":
        problems.append(f"HTTP {values.get('ha_http')} on :8123")
    fs_state = values.get("fs_state", "")
    if "with errors" in fs_state:
        problems.append(
            f"/userdata filesystem has errors (state '{fs_state}', "
            f"{values.get('fs_error_count', '?')} since last fsck)"
        )
    if values.get("fs_journal") == "0":
        problems.append("/userdata ext4 has no journal: every power cut corrupts it")
    userdata_free = _int_or_none(values.get("userdata_free_mb"))
    if userdata_free is not None and userdata_free < 250:
        problems.append(f"/userdata free {userdata_free} MB < 250")
    root_free = _int_or_none(values.get("root_free_mb"))
    if root_free is not None and root_free < 800:
        problems.append(f"root free {root_free} MB < 800")
    if values.get("backup_mount_nfs") == "0":
        problems.append("NAS backup share is not mounted")
    backup_age = _int_or_none(values.get("backup_age_h"))
    if backup_age is None:
        problems.append("no HA backup archive found on NAS")
    elif backup_age > 48:
        problems.append(f"newest HA backup is {backup_age} h old")
    backup_size = _int_or_none(values.get("backup_size_mb"))
    if backup_size is not None and backup_size > 1024:
        problems.append(
            f"newest HA backup is {backup_size} MB: it is dragging NAS media, "
            "not settings only"
        )
    if values.get("tailscale") == "logged_out":
        problems.append("tailscale is logged out (Cloudflare is the only remote path)")
    if values.get("cloudflared") != "active":
        problems.append("cloudflared-ha is not active")
    if values.get("inverter_ping") != "ok":
        problems.append("Deye logger 192.168.50.179 does not answer: outage automations are blind")
    if values.get("well_pump_ping") != "ok":
        problems.append(f"well pump plug {WELL_PUMP_IP} does not answer")
    orphaned = _int_or_none(values.get("automations_orphaned"))
    if orphaned:
        problems.append(f"{orphaned} automation/script registry entries are orphaned (unavailable)")
    if values.get("states_error"):
        problems.append(f"could not read /api/states: {values['states_error']}")
    return {
        "healthy": not problems,
        "problems": problems,
        "values": values,
        "transport": result,
    }


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
            "LocalTuya 3.5 relay over LAN TCP/6668 with a 1-second scan; the "
            "local power entity is the monitoring source since 2026-08-22"
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
                "LocalTuya scan_interval is 1 s (set 2026-08-22; without it the "
                "plug reported 0-28 % of a run). A missing session here means "
                "the plug is off the LAN, not that local telemetry is broken"
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


def entity_states(pattern: str, limit: int = 200) -> dict[str, Any]:
    """Read matching entity states through HA's own REST API on the board.

    Повертає лише entity_id, стан, одиницю, friendly_name і час зміни - жодних
    атрибутів, у яких можуть жити координати, ключі чи URL. Токен читається на
    платі і ніколи не повертається. До 02.09.2026 агент збирав це curl-конвеєром
    вручну в кожній сесії.
    """
    if not pattern or len(pattern) > 200:
        raise ValueError("pattern is required and limited to 200 characters")
    re.compile(pattern)  # validate locally before sending
    limit = max(1, min(int(limit), 500))
    remote_script = f"""
import json, os, re, urllib.request
token_path = {HA_TOKEN_FILE!r}
if not os.path.isfile(token_path):
    print(json.dumps({{'_error': 'token_missing'}})); raise SystemExit(0)
token = open(token_path, encoding='utf-8').read().strip()
req = urllib.request.Request('http://localhost:8123/api/states', headers={{'Authorization': 'Bearer ' + token}})
states = json.load(urllib.request.urlopen(req, timeout=15))
rx = re.compile({pattern!r}, re.I)
out = []
for s in sorted(states, key=lambda s: s['entity_id']):
    if rx.search(s['entity_id']) or rx.search(str(s['attributes'].get('friendly_name', ''))):
        out.append({{'entity_id': s['entity_id'], 'state': s['state'],
                    'unit': s['attributes'].get('unit_of_measurement'),
                    'name': s['attributes'].get('friendly_name'),
                    'last_changed': s['last_changed']}})
print(json.dumps({{'matched': len(out), 'entities': out[:{limit}]}}, ensure_ascii=False))
""".strip()
    transport = _ssh(
        f"{shlex.quote(HA_VENV)}/bin/python -c " + shlex.quote(remote_script),
        timeout=60,
    )
    if not transport["ok"]:
        return {"ok": False, "matched": 0, "entities": [], "transport": transport}
    try:
        data = json.loads(transport["stdout"])
    except json.JSONDecodeError:
        return {"ok": False, "matched": 0, "entities": [], "transport": transport}
    if data.get("_error"):
        return {"ok": False, "reason": data["_error"], "matched": 0, "entities": []}
    return {"ok": True, "matched": data["matched"], "entities": data["entities"]}


NOTIFY_LOG_SCRIPT = f"{HA_CONFIG_ROOT}/scripts/notify_log.py"


def notify_log(limit: int = 40) -> dict[str, Any]:
    """Read the board's notification journal (notifications.db) via its own script.

    Це той самий журнал, що показує вкладка «Пристрої → Сповіщення»: кожен
    виклик notify.* і persistent_notification.create, з позначкою «нове» і
    згорнутими дублями на три телефони. Лише читання.
    """
    limit = max(1, min(int(limit), 200))
    transport = _ssh(
        f"{shlex.quote(HA_VENV)}/bin/python {shlex.quote(NOTIFY_LOG_SCRIPT)} export --limit {limit}",
        timeout=60,
    )
    if not transport["ok"]:
        return {"ok": False, "transport": transport}
    try:
        data = json.loads(transport["stdout"])
    except json.JSONDecodeError:
        return {"ok": False, "transport": transport}
    data["ok"] = True
    return data


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
