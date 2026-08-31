---
name: home-assistant
description: Safely inspect, operate, diagnose, and update the production Home Assistant Core 2026.7.4 deployment at 192.168.50.141, including its migrated standalone config and venv. Use for Home Assistant YAML, dashboards, automations, integrations, irrigation, well-water and pump monitoring, energy, network inventory, NAS backups/logs, voice/Claude integration, board health, repository synchronization, deployment, validation, reloads, and restarts.
---

# Production Home Assistant on MB35x8

## Start with the project MCP

Use the project-local `home-assistant-project` MCP server when it is available.
Prefer its read-only tools for health, irrigation and well-pump LocalTuya
readiness, Git status, router inventory, logs, config validation, and
board/repository hash comparison. It intentionally has no tool that edits
`.storage`, the recorder database, or live configuration.

If the MCP server is not registered, run the same checks with
`python mcp-server/cli.py health`, `sync`, `git`, `inventory`, `logs`, or
`validate`, `irrigation-health`, `well-pump-health`, or `energy-flow-health`
from the repository root. Use `energy-flow-health` before changing the Deye
power-flow card or treating the inverter grid sensor as whole-site demand.

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
   This bans touching those files. It does **not** ban Home Assistant's own
   WebSocket APIs, which own that same data and are the correct way in:
   `recorder/statistics_during_period` and `recorder/adjust_sum_statistics`
   instead of opening the database, `lovelace/resources/update` instead of
   editing `.storage/lovelace_resources`. Authenticate with the token from
   `/home/forlinx/.ha_token`; never print it. If that file is missing, restore it
   with `scripts/install-ha-token.sh` — without it `house-analyst.service`, the
   MCP `energy-flow-health` check and every statistics tool fail at once.
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
11. The owner identifies the current physical replacement as RK3588, while its
    migrated Linux image currently reports `Forlinx OK3568-C` and
    `rockchip,rk3568`. Treat `.141` as the production target, but record both
    facts and do not infer that a different host is production from the stale
    hostname or Device Tree label alone.

## Connection and canonical paths

```powershell
$key = 'C:\SPB_Data\.ssh\mb35x8_ed25519'
ssh.exe -i $key -o BatchMode=yes forlinx@192.168.50.141
```

`sudo` is passwordless for `forlinx`.

| Item | Value |
|---|---|
| Board | Current MB35x8 production replacement; owner: RK3588; migrated OS currently reports OK3568-C/RK3568 |
| HA | Core 2026.7.4, Python 3.14.6 |
| Venv | `/userdata/hass/venv` → `/home/forlinx/hass-venv` |
| Config | `/userdata/hass/config` → `/userdata/hass/config-standalone` |
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
/userdata/hass/venv/bin/hass --script check_config -c /userdata/hass/config
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

## Custom Lovelace cards

Nine cards live in `/userdata/hass/config/www/*.js` and carry a large part of the
water and energy dashboards. Until 2026-08-30 eight of the nine existed only on
the board: they were outside Git and outside `SYNC_TARGETS`, so a wrong card
could not be reviewed, diffed or rolled back. They are now both.

Three rules when touching them:

- **Deploy like any other file** — back up to the NAS, upload to `.new`, verify,
  rename atomically. No reload or restart is needed; cards are static assets.
- **Bump the resource version, always.** Changing the file is not enough: the
  browser caches the module under its unchanged `/local/…js?v=N` URL, and on
  2026-08-30 a corrected card kept drawing the old chart on every device. Use
  the API — `lovelace/resources` to list, `lovelace/resources/update` with
  `resource_id`, `res_type: "module"` and the url rewritten to `?v=N+1`. A hard
  refresh is a hope, not a fix, and it does nothing for the phone in another room.
- **Cards read raw history, not statistics.** They walk
  `/api/history/period` and sum deltas themselves, so they get none of the
  recorder's own reset handling. Any card that sums deltas needs a guard against
  a source that dips: see the worked example in `references/well-water.md`, where
  a 0.038 kWh dip after a restart was read as a counter reset and printed a
  5 148 L bar instead of 618 L.

Three NFS mount units are deliberately absent from `SYNC_TARGETS`: their names
contain systemd escaping with a backslash
(`userdata-hass-config\x2dstandalone-backups.mount`), which is not a legal
filename on the Windows working copy. They are started by `nas-mounts.service`,
which is tracked.

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
