---
name: home-assistant
description: Safely inspect, operate, diagnose, and update the production Home Assistant Core 2026.7.4 deployment at 192.168.50.141, including its migrated standalone config and venv. Use for Home Assistant YAML, dashboards, automations, integrations, irrigation, well-water and pump monitoring, energy, network inventory, NAS backups/logs, voice/Claude integration, board health, repository synchronization, deployment, validation, reloads, and restarts.
---

# Production Home Assistant on MB35x8

## Start with the project MCP

Use the project-local `home-assistant-project` MCP server when it is available.
Prefer its read-only tools for health, irrigation and well-pump LocalTuya
readiness, Git status, router inventory, logs, config validation, entity
states (`ha_entity_states`, a regex over entity ids and names), the
notification journal (`ha_notify_log`), and board/repository hash comparison.
It intentionally has no tool that edits `.storage`, the recorder database, or
live configuration.

If the MCP server is not registered, run the same checks with
`python mcp-server/cli.py health`, `sync`, `git`, `inventory`, `logs`,
`states '<regex>'`, `notify-log`, `validate`, `irrigation-health`,
`well-pump-health`, or `energy-flow-health` from the repository root. Use
`energy-flow-health` before changing the Deye power-flow card or treating the
inverter grid sensor as whole-site demand.

**An MCP timeout is not proof that the board is down.** On 2026-09-02 every MCP
tool timed out for half an hour while a direct `ssh.exe … uptime` answered in a
second: the tools were synchronous and blocked the server's event loop, so
parallel calls queued and summed each other's timeouts. They are async now, but
the rule stays: after a timeout, run one direct SSH command before concluding
anything about the board.

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
- Read `references/tuya.md` before binding anything to a Tuya entity, judging
  what a Tuya account or subscription outage would break, or touching the
  `tuya`/`localtuya` config entries. It carries the cloud-vs-local inventory:
  which devices have a local twin and which seven are cloud-only.
- Read `references/outage.md` before touching anything that reacts to a power
  cut: the grid sensor, the battery thresholds, the load-shedding automation,
  the inverter watchdog, or the readiness guard. It also explains what the
  board itself does when the power goes (it goes down too).
- Read `references/notifications.md` before adding a push, a persistent
  notification, or any card that shows alerts: every notification is journaled
  on the board, and the journal has rules about duplicates and reading.
- Read the top of `docs/worklog.md` (журнал робіт) before diagnosing anything:
  it is the dated record of findings, decisions the owner made and what is
  still pending, with commit ids. `docs/incident-register.md` holds the open
  technical problems with evidence. Both exist so a new session does not
  rediscover what a previous one already proved.

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
11. Never bind an automation, a `utility_meter`, or an Energy dashboard source
    to a cloud Tuya entity when a LocalTuya twin exists; see
    `references/tuya.md` for the twin table and the two deliberate exceptions.
    The cloud copy belongs on a dashboard as a manual fallback, or as the last
    retry inside an automation — never as the only path. Ignoring this has
    already cost ten days of grid statistics and a day of hot water.
12. The owner identifies the current physical replacement as RK3588, while its
    migrated Linux image currently reports `Forlinx OK3568-C` and
    `rockchip,rk3568`. Treat `.141` as the production target, but record both
    facts and do not infer that a different host is production from the stale
    hostname or Device Tree label alone.
13. Never put `initial:` on an `input_number`, `input_boolean` or
    `input_select` that the dashboard is meant to own. It resets the value on
    every restart, and the board restarts with every power cut: the outage
    thresholds silently went back to their defaults for weeks before 2026-09-02.
    `counter` keeps `initial` because its daily reset relies on it.
14. Never mount NAS data anywhere under `/userdata/hass/config*/`. Core's
    backup archives the whole config tree, mounts and bind mounts included
    (`media/*` is NOT excluded); camera clips mounted there made every nightly
    archive 5-9 GB and abort mid-tar, so no backup completed between 11.08 and
    03.09.2026. Mount under `/mnt/homemate_media/` and symlink from `media/`;
    serve clips through `media_source` signed URLs, never a `www` bind
    (`/local/` refuses symlinks outside `www/`). See `references/platform.md`.
15. End every working session by appending to `docs/worklog.md`: findings with
    numbers, what was done with commit ids, the owner's decisions verbatim,
    what is pending and who closes it. Update the skill or its references in
    the same commit when a rule changed. The owner asked for this explicitly on
    2026-09-03; a finding that lives only in the conversation is lost.
16. The GitHub repository `SenseProg/HomeAssistant` is **public** (checked
    2026-09-03). Nothing that goes into Git - YAML comments, docs, the worklog,
    the skill - may carry personal data (family names with roles, e-mails,
    phone models, MAC addresses tied to rooms), public URLs of camera frames
    or photos, tokens, or private-key paths. The revision of 03.09 found all of
    these already in the tree; until the owner makes the repository private or
    cleans it, do not add more, and write worklog entries about exposures in
    general terms.

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
python mcp-server/cli.py dashboards
python mcp-server/cli.py incidents
```

Then read the newest entry of `docs/worklog.md`. If every localhost API call on
the board answers `403: Forbidden` while the browser works, HA has banned
127.0.0.1 (`ip_bans.yaml`): the board booted with its dead RTC on 2024 and the
token looked "not yet valid". Use `http://192.168.50.141:8123` from the board
instead, remove the entry from `ip_bans.yaml`, and the ban lifts at the next
restart (`references/platform.md`, "No RTC").

`incidents` reads the board's register of open technical problems, the same list
the conversation agent sees in its `<known_incidents>` block. Read it before
diagnosing anything: a symptom that is already recorded does not need
rediscovering, and a record marked `watching` is waiting for exactly the kind of
confirmation a new session can give. See `docs/incident-register.md`.

`health` returns `problems`: a plain-language list of everything that failed —
filesystem errors or a missing ext4 journal on `/userdata`, a backup older than
48 h or larger than 1 GB (it is dragging NAS media), a logged-out Tailscale,
an inactive Cloudflare tunnel, an unreachable Deye logger or well-pump plug,
orphaned automation entities. Since 2026-09-03 it also reports a wrong board
clock (`clock_year`), an HA process that started under the 2024 clock
(`ha_started_year`; cloud integrations then sit in `setup_error` until a
restart), a banned localhost (403 on localhost while `ha_http_lan` is 200),
config entries that failed to set up (`entries_setup_error`), inverter
entities unavailable while the logger pings, a backup "in the future" (clock
behind the NAS), more than a quarter of all entities unavailable, and the
photo/video NAS mounts. `healthy` is true only when that list is empty.
Until 2026-09-02 it said `healthy: true` beside a corrupted filesystem; do not
trust any older memory that says otherwise. If the list is not empty, also run
`python mcp-server/cli.py notify-log` — the board has usually been telling the
owner about it for days.

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
| Storage dashboard (`notifications_dashboard.yaml`, `sverdlovina_dashboard.yaml`) | copy the file, then `scripts/lovelace_push.py <file> <url_path>` on the board; no reload |
| `automations.yaml` | `automation.reload` |
| `scripts.yaml` | `script.reload` |
| Reloadable template entities | `template.reload` |
| `command_line:` sensors, `shell_command:` entries | `command_line.reload`, `shell_command.reload` — both verified on 2026-09-02 |
| Helpers (`input_number`, `input_boolean`, `input_select`) | `input_number.reload` etc. |
| Custom card `.js` | copy, then bump `?v=` with `scripts/ha_admin.py resources --bump /local/<card>.js` |
| Dashboard registration/resources in `configuration.yaml`, `recorder:`, `logger:` | Check config, restart |
| Integration install, Python package, systemd unit, custom integration code | Check config, restart |

The deploy helper lives on the board at `/home/forlinx/deploy.sh` (source:
`board-config/scripts/deploy.sh`; do not keep it in `/tmp` - `systemd-tmpfiles`
wiped `/tmp/deploy.sh` and the `/tmp/deploy` staging dir mid-session on
2026-09-03). Stage with `scp` into `/tmp/deploy/<name>` (recreate the dir), then:

```bash
bash /home/forlinx/deploy.sh deploy <stamp> <name>:<target>:<sha256> ...
bash /home/forlinx/deploy.sh reload automation command_line shell_command
```

It verifies the staged sha256, copies the current target to the NAS
`backups/deployment-rollback/<name>.bak-<stamp>`, writes `<target>.new`, renames
atomically and verifies again; `reload` falls back to the LAN address when
localhost is banned. Validate with `python mcp-server/cli.py validate` from the
workstation. `allowlist_external_dirs` entries must exist as directories or
`check_config` fails - create the mount point before validating.

Three traps confirmed by the revision of 2026-09-03:

- **CRLF.** The Windows working copy keeps 66 tracked files with CRLF
  (`core.autocrlf=true`; `.gitattributes` covers only four files): every unit
  in `new-board/systemd/`, `timesync-retry.*`, `tv-photo-*.sh`,
  `homemate-nas-sync.sh`, `scripts.yaml`, `project_tools.py`. The board copies
  are LF, which is what `sync` reports as `match_eol_only`. Never `scp` such a
  file to the board as it is: strip CR on the staged copy
  (`sed -i 's/\r$//'`) or fix it at the root with `board-config/** text eol=lf`
  and `mcp-server/** text eol=lf` in `.gitattributes` plus
  `git add --renormalize .`.
- **systemd `$` and `+`.** Verified with a real unit file on 2026-09-04: a
  `$i` embedded inside the quoted `sh -c '...'` string is NOT touched by
  systemd (it prints i=1, i=2); only a whole-word `$VAR` argument or `${VAR}`
  is substituted, and `%` must be written `%%`. The earlier claim that `$$i`
  is required was wrong - do not "fix" it. What is real: `ExecStartPre=` runs
  as the unit's `User=forlinx`, so prefix the executable with `+` when the
  command needs root (`wait-for-clock.conf` has it since 04.09).
- **`www/` is public.** Home Assistant serves `www/` as `/local/` without
  authentication and the Cloudflare tunnel forwards it to the internet
  (checked from outside on 2026-09-03: camera frames in `www/motion/`,
  `clips.json`, the TV photo and `www/analyst/latest.json` answered 200).
  Never put camera frames, family photos, analyst output or anything with a
  token under `www/`; use `media/` with signed URLs, and put Cloudflare Access
  in front of the hostname.

Reloads are plain HTTP calls on the board and pass the permission classifier:

```bash
TOKEN=$(cat /home/forlinx/.ha_token)
curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -X POST \
  http://localhost:8123/api/services/automation/reload -d '{}'
```

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

## Storage dashboards, the entity registry and integrations: through the API

Rule 1 bans the files, not the API that owns them. Everything below is done
with Home Assistant's own WebSocket/REST calls, from scripts that live in
`board-config/scripts/` and run on the board with the token file:

- **Storage dashboards.** «Сповіщення» (`spovishchennia-zhurnal`) and
  «Свердловина» (`sverdlovina-dashboard`) are storage-mode dashboards whose
  source of truth is a repo file. `scripts/lovelace_push.py <file> <url_path>`
  creates the dashboard if missing (`lovelace/dashboards/create`) and saves the
  config (`lovelace/config/save`); `--dump` prints the live config. Because the
  owner can also edit them in the UI, run `python mcp-server/cli.py dashboards`
  (MCP `ha_storage_dashboards`) before editing the file: `mismatch` means pull
  the live config with `--dump` and merge, never overwrite blindly. This is
  also how a YAML page can go live without the restart that
  `lovelace.dashboards` registration needs.
- **Registry and statistics.** `scripts/ha_admin.py orphans [--remove]`
  lists and deletes automation/script/helper entities that were removed from
  YAML but stayed in the registry as `unavailable` (18 of them on 2026-09-02
  were what the owner saw as "automations flying off");
  `stats-units [--fix]` relabels `*_za_tarifom_*` statistics whose unit became
  `None`; `resources [--bump URL]`, `drawer`, `dashboards`, `repairs` read the
  rest.
- **Integrations.** A config flow can be driven through REST:
  `POST /api/config/config_entries/flow {"handler": "<domain>"}` returns the
  first step and its `data_schema`; `POST …/flow/<flow_id>` with the answers
  walks the steps until `create_entry`. Yasno was configured this way on
  2026-09-02. Ask the owner for the inputs (address, group, credentials);
  never guess them.

## What the permission classifier allows on this host (observed 2026-09-02/03)

- Passes: `scp` to `/tmp/deploy`, the backup + `.new` + `mv` deploy script,
  `curl` reload calls, config flows and WebSocket admin scripts, `git commit`
  and `git push`, config-flow REST calls, `sudo mkdir`, `sudo install` of a
  systemd drop-in plus `systemctl daemon-reload`, a service-management script
  under `nohup` (the fsck script that stops and starts HA itself), HA service
  calls that switch real devices when the owner asked for it.
- Blocked, consistently: `sudo systemctl restart home-assistant`, any single
  command that combines a deploy with reloads or restarts, and a batch that
  disables a mount unit and deletes its unit file. Do not work around it;
  finish everything else and hand the owner one script that does the
  privileged part (pattern: `board-config/new-board/finish-video-move.sh`).
- `deploy.sh` falls back to `sudo -n cp/mv` for targets outside `/userdata`;
  a `/etc` deploy may still be refused - keep it in the owner's script.

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

Since 2026-09-03 `SYNC_TARGETS` covers both systemd folders of the repo
(`board-config/systemd/` and `board-config/new-board/systemd/`, including the
`wait-for-clock.conf` drop-in), the 03.09 version of `nas-mounts.service`
from `new-board/systemd/` (the pre-03.09 copy with the `www/motion-clips`
bind still sits in `board-config/systemd/` only because the permission
classifier blocks file deletion from an agent session; it is excluded from
sync and waits for the owner to delete it, together with the byte-identical
duplicates `new-board/home-assistant.service`,
`new-board/systemd/netplan-fallback.service` and `new-board/default-tailscaled`),
and the owner's scripts `/home/forlinx/deploy.sh` and
`/home/forlinx/fsck-userdata.sh`. Two entries are expected to be off until
the owner runs `finish-video-move.sh`: `nas-mounts.service` shows `mismatch`
(the board still runs the old unit) and `mnt-homemate_media-video.mount` shows
`remote_missing`. One NFS mount unit stays out deliberately: its name on the
board carries systemd escaping (`userdata-hass-config\x2dstandalone-backups.mount`),
which is not a legal Windows filename and which GNU `sha256sum` escapes in its
output; `nas-mounts.service` starts it. The test
`test_sync_targets_cover_every_systemd_unit_in_repo` fails if a unit file is
added to either folder without a sync entry.

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
- Every commit that changes behaviour comes with a `docs/worklog.md` entry
  (same commit or the session's closing one).

The MCP server and both project skills are part of this repository so every
session uses the same operational rules as the configuration it modifies.
