---
name: home-assistant
description: Safely inspect, operate, diagnose, and update the Home Assistant Core 2026.7.4 deployment on the MB35x8/Forlinx RK3568J board at 192.168.50.141. Use for Home Assistant YAML, dashboards, automations, integrations, irrigation, well-water and pump monitoring, energy, network inventory, ASUS DHCP naming, NAS backups/logs, voice/Claude integration, board health, repository-to-board synchronization, and any request to add, rename, troubleshoot, deploy, validate, reload, or restart this smart-home system.
---

# Home Assistant on MB35x8

## Start with the project MCP

Use the project-local `home-assistant-project` MCP server when it is available.
Prefer its read-only tools for health, irrigation and well-pump LocalTuya
readiness, Git status, router inventory, logs, config validation, and
board/repository hash comparison. It intentionally has no tool that edits
`.storage`, the recorder database, or live configuration.

If the MCP server is not registered, run the same checks with
`python mcp-server/cli.py health`, `sync`, `git`, `inventory`, `logs`, or
`validate`, `irrigation-health`, or `well-pump-health` from the repository root.

## Read the relevant reference

- Read `references/platform.md` for paths, services, storage, zram, NAS, timezones,
  and board limitations.
- Read `references/network.md` for fixed IP/MAC inventory, ASUS naming, presence,
  Tenda topology, cameras, recuperators, and unknown-device identification.
- Read `references/irrigation.md` before changing any pump, valve, irrigation
  schedule, Smart Irrigation setting, or safety automation.
- Read `references/energy.md` for Energy dashboard sources, per-device power and
  energy, charging, boiler, inverter, and delayed-statistics behavior.
- Read `references/well-water.md` before changing the well-pump plug, its
  LocalTuya entities, one-second scan, energy integrator, water calibration,
  mechanical readings, or the `sverdlovina-dashboard` storage dashboard.

## Non-negotiable safety rules

1. Never read, copy, edit, commit, or disclose `/userdata/hass/config/.storage/`,
   `secrets.yaml`, the recorder database, tokens, passwords, or local keys.
2. Before editing, compare Git with the board. A clean Git tree does not prove
   the board matches the repository. Use `repo_board_sync`/`cli.py sync`.
3. If a target file differs, pull it to a temporary path and inspect the diff.
   Do not overwrite either side until the divergence is understood.
4. Back up every live file before replacing it. Use a timestamped sibling such
   as `file.yaml.bak-YYYYMMDD-HHMMSS`.
5. Copy through a temporary live path, verify it, then rename atomically.
6. Run `hass --script check_config` before every required HA restart.
7. Use the smallest reload scope. Do not restart HA for dashboard-only content,
   names, or ordinary automation/script changes.
8. Never restart while irrigation is running or a multi-step integration flow is
   open. Confirm pump and every physical valve are off first.
9. Do not add `-b 192.168.50.111` to SSH. That bridge no longer exists.
10. Do not reconfigure or flash the board to obtain Docker. The vendor kernel
    lacks overlayfs, veth, and required cgroups.

## Connection and canonical paths

```powershell
$key = 'C:\SPB_Data\.ssh\mb35x8_ed25519'
ssh.exe -i $key -o BatchMode=yes forlinx@192.168.50.141
```

`sudo` is passwordless for `forlinx`.

| Item | Value |
|---|---|
| Board | MB35x8 v1.0 + Forlinx RK3568J, Ubuntu 20.04.6, aarch64 |
| HA | Core 2026.7.4, Python 3.14.6 |
| Venv | `/home/forlinx/hass-venv-314` |
| Config | `/userdata/hass/config` |
| Service | `home-assistant.service` |
| UI | `http://192.168.50.141:8123/` |
| Repository | `SenseProg/HomeAssistant`, local clone `E:\Work\Pojects\HA` |

## Begin every session

```powershell
python mcp-server/cli.py git
python mcp-server/cli.py health
python mcp-server/cli.py sync
python mcp-server/cli.py incidents
```

`incidents` reads the board's register of open technical problems, the same list
the conversation agent sees in its `<known_incidents>` block. Read it before
diagnosing anything: a symptom that is already recorded does not need
rediscovering, and a record marked `watching` is waiting for exactly the kind of
confirmation a new session can give. See `docs/incident-register.md`.

Treat any `mismatch` result as a stop condition for deployment. `match_eol_only`
is not one: the text is identical and only the line endings differ, which is
what the Windows working copy does to files the board itself owns — the four
systemd units are permanently in that state. Pull the live
copy to a temporary directory and use `git diff --no-index` to understand it.
The board is the runtime truth; Git is the intended-state truth. Neither should
silently replace the other.

## Deploy a file safely

1. Fetch and compare the live target immediately before editing.
2. Edit the repository file.
3. Validate YAML locally when possible.
4. Create a timestamped rollback copy according to the backup rules in
   `references/platform.md`. Never leave it under `/userdata` or the HA
   `backups/` directory.
5. Upload to `<target>.new`, verify ownership and content, then atomically rename.
6. Apply the smallest scope from the table below.
7. Re-run `sync`, check the HA service and HTTP 200, then commit only intended
   repository files.

| Change | Apply |
|---|---|
| Existing YAML dashboard content | Browser hard refresh; no HA restart |
| `automations.yaml` | `automation.reload` |
| `scripts.yaml` | `script.reload` |
| Reloadable template entities | `template.reload` |
| Command-line integration entities | `command_line.reload` when supported |
| Dashboard registration/resources in `configuration.yaml` | Check config, restart |
| Integration install, Python package, systemd unit | Check config, restart |

Config validation:

```bash
/home/forlinx/hass-venv-314/bin/hass --script check_config -c /userdata/hass/config
```

After a required restart, allow up to 90 seconds, then verify:

```bash
systemctl is-active home-assistant
curl -s -o /dev/null -w '%{http_code}' http://localhost:8123/
```

LocalTuya may show `unknown` for roughly three minutes after startup. Do not
change it during that recovery window.

For the well pump, run `ha_well_pump_health` or
`python mcp-server/cli.py well-pump-health` before changing its monitoring path.
Do not confuse this T34 plug with the irrigation pump at `.91`; the two pumps
have different entity models and safety rules.

## Diagnose before changing

Use evidence in this order:

1. `board_health` or `cli.py health`.
2. `recent_home_assistant_logs` or `cli.py logs`.
3. `systemctl show home-assistant -p ActiveEnterTimestamp --value`.
4. `uptime`, `last -x reboot`, and `journalctl --list-boots` to distinguish a
   board power loss from a Home Assistant process failure.
5. `df -h / /userdata` before reauthenticating integrations. A full filesystem
   can surface as an authentication error because HA cannot persist tokens.

Do not interpret recorder's unclean-shutdown warning as the cause of a failure;
it is usually a consequence of abrupt power loss. Terneo `Failed to parse JSON`
means the thermostat/API is unreachable and is not evidence that recorder fell.

## Router and device naming

Use ASCII DHCP hostnames such as `Deye-Inverter` and
`PRANA-Parents-Bedroom`. Keep the existing MAC and reserved IP unchanged.
In stock ASUS firmware, changing a hostname means deleting the local row,
re-adding the same MAC/IP with a hostname, then applying. Apply logs the admin
session out because DHCP/web services restart. Log in again and verify the
persisted row. This is a router operation, not a reason to restart HA.

Never store ASUS credentials in the repository, skill, MCP configuration, or
shell history. Use an already authenticated browser or credentials explicitly
provided for the current operation only.

## Version control

- Preserve unrelated user changes and untracked files.
- Stage explicit paths, never `git add -A` in a dirty tree.
- Never commit `.storage`, databases, logs, credentials, backups, or media.
- Pull/fetch before editing and compare the current branch to its upstream.
- Push only after validation succeeds.

The MCP server and both project skills are part of this repository so every
session uses the same operational rules as the configuration it modifies.
