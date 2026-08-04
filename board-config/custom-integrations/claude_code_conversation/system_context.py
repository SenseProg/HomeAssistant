"""Bounded read-only operating-system context for Claude Assist."""

import asyncio
from collections.abc import Sequence
from pathlib import Path
import time

from . import ClaudeCodeConfigEntry
from .const import SYSTEM_CONTEXT_MAX_CHARS, SYSTEM_CONTEXT_TTL_SECONDS

_CORE_COMMANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Ядро", ("/usr/bin/uname", "-a")),
    ("Час роботи", ("/usr/bin/uptime", "-p")),
    ("Пам'ять", ("/usr/bin/free", "-m")),
    ("Файлові системи", ("/usr/bin/df", "-hT", "/", "/userdata")),
    (
        "Монтування",
        ("/usr/bin/findmnt", "-rn", "-o", "TARGET,SOURCE,FSTYPE"),
    ),
    ("ZRAM", ("/usr/sbin/zramctl",)),
    ("Мережеві адреси", ("/usr/sbin/ip", "-brief", "address")),
    ("Маршрути", ("/usr/sbin/ip", "route")),
    ("TCP-порти", ("/usr/bin/ss", "-lnt")),
    (
        "Процеси за RAM",
        (
            "/usr/bin/ps",
            "-eo",
            "pid,comm,%cpu,%mem,rss",
            "--sort=-rss",
        ),
    ),
    (
        "Несправні systemd-служби",
        ("/usr/bin/systemctl", "--failed", "--no-legend", "--plain"),
    ),
    (
        "Ключові служби",
        (
            "/usr/bin/systemctl",
            "show",
            "home-assistant",
            "homemate-nas-sync.timer",
            "house-analyst.timer",
            "--property=Id,LoadState,ActiveState,SubState,UnitFileState,MainPID,MemoryCurrent,NRestarts",
        ),
    ),
    (
        "Таймери systemd",
        (
            "/usr/bin/systemctl",
            "list-timers",
            "--all",
            "--no-legend",
            "--plain",
        ),
    ),
)

_LOG_COMMANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Home Assistant warning/error за 2 години",
        (
            "/usr/bin/sudo",
            "-n",
            "/usr/bin/journalctl",
            "-u",
            "home-assistant",
            "-p",
            "warning",
            "--since=-2h",
            "--no-pager",
            "-n",
            "80",
        ),
    ),
    (
        "Kernel warning/error",
        (
            "/usr/bin/sudo",
            "-n",
            "/usr/bin/dmesg",
            "--level=err,warn",
        ),
    ),
)

_LOG_REQUEST_MARKERS = (
    "авар",
    "впав",
    "журнал",
    "лог",
    "падін",
    "помил",
    "причин",
    "систем",
    "dmesg",
    "error",
    "journal",
    "log",
    "oom",
)


def _read_fixed_files() -> str:
    """Read a small allowlist of non-secret OS facts."""
    sections: list[str] = []
    try:
        os_release = Path("/etc/os-release").read_text(encoding="utf-8")
        allowed = {
            line
            for line in os_release.splitlines()
            if line.startswith(("NAME=", "VERSION=", "PRETTY_NAME=", "ID=", "VERSION_ID="))
        }
        sections.append("[Операційна система]\n" + "\n".join(sorted(allowed)))
    except OSError as err:
        sections.append(f"[Операційна система]\nнедоступно: {type(err).__name__}")

    thermal_lines: list[str] = []
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        try:
            zone_type = (zone / "type").read_text(encoding="utf-8").strip()
            raw = float((zone / "temp").read_text(encoding="utf-8").strip())
            celsius = raw / 1000 if raw > 500 else raw
            thermal_lines.append(f"{zone.name} {zone_type}: {celsius:.1f} °C")
        except (OSError, ValueError):
            continue
    sections.append(
        "[Температури]\n"
        + ("\n".join(thermal_lines) if thermal_lines else "немає доступних датчиків")
    )
    return "\n\n".join(sections)


async def _run_command(args: Sequence[str], limit: int = 6000) -> str:
    """Run one fixed read-only command with timeout and bounded output."""
    env = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"}
    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        async with asyncio.timeout(5):
            stdout, stderr = await process.communicate()
    except (FileNotFoundError, PermissionError) as err:
        return f"недоступно: {type(err).__name__}"
    except TimeoutError:
        process.kill()
        await process.wait()
        return "недоступно: timeout"

    output = stdout.decode("utf-8", errors="replace").strip()
    error = stderr.decode("utf-8", errors="replace").strip()
    if process.returncode != 0:
        output = f"код {process.returncode}: {error or output}"
    elif not output:
        output = "немає записів"
    return output[:limit]


def _needs_logs(user_text: str) -> bool:
    """Include privileged read-only logs only for diagnostic questions."""
    lowered = user_text.casefold()
    return any(marker in lowered for marker in _LOG_REQUEST_MARKERS)


async def async_system_snapshot(
    entry: ClaudeCodeConfigEntry, user_text: str
) -> str:
    """Return cached core diagnostics and optional fresh logs."""
    runtime = entry.runtime_data
    now = time.monotonic()
    async with runtime.system_lock:
        if (
            runtime.system_snapshot is None
            or now - runtime.system_snapshot_monotonic > SYSTEM_CONTEXT_TTL_SECONDS
        ):
            fixed_files, command_results = await asyncio.gather(
                asyncio.to_thread(_read_fixed_files),
                asyncio.gather(*(_run_command(args) for _label, args in _CORE_COMMANDS)),
            )
            sections = [fixed_files]
            sections.extend(
                f"[{label}]\n{result}"
                for (label, _args), result in zip(
                    _CORE_COMMANDS, command_results, strict=True
                )
            )
            runtime.system_snapshot = "\n\n".join(sections)[
                :SYSTEM_CONTEXT_MAX_CHARS
            ]
            runtime.system_snapshot_monotonic = now
        snapshot = runtime.system_snapshot

    if not _needs_logs(user_text):
        return snapshot

    log_results = await asyncio.gather(
        *(_run_command(args, limit=10000) for _label, args in _LOG_COMMANDS)
    )
    log_sections = "\n\n".join(
        f"[{label}]\n{result}"
        for (label, _args), result in zip(_LOG_COMMANDS, log_results, strict=True)
    )
    return (snapshot + "\n\n" + log_sections)[:SYSTEM_CONTEXT_MAX_CHARS]
