# Platform and services

## Runtime

- Board: current MB35x8 production replacement, identified by the owner as
  RK3588. The migrated Linux image still reports `Forlinx OK3568-C Board` and
  `rockchip,rk3568`; preserve this discrepancy as an observed fact rather than
  choosing another deployment target from the stale label.
- OS: Ubuntu 20.04.6 LTS, kernel 4.19.206, aarch64, 4 cores, **1.93 GiB RAM**
  (MemTotal 2 019 024 kB, measured 2026-08-22; the 3.8 GiB in older documents
  was wrong, and the board runs close to swap when a voice model is preloaded).
- Host/IP: legacy hostname `ok3568`, `192.168.50.141` on `eth0`; `.168` is a
  secondary address on the same interface.
- Home Assistant: Core 2026.7.4 in `/userdata/hass/venv` (a symlink to
  `/home/forlinx/hass-venv`) using
  Python 3.14.6.
- Config: `/userdata/hass/config`, a symlink to
  `/userdata/hass/config-standalone`.
- Service: `home-assistant.service`.
- HA and board OS timezone: `Europe/Kyiv`.

## Storage and memory

- The root filesystem contains the venv and Node/Claude tooling.
- `/userdata` contains HA config and recorder data.
- **`/userdata` is ext4 with a journal since 2026-09-03 09:06.** Until then it
  had no `has_journal`, was mounted `errors=continue` with `pass 0`, and the
  board — which is not on protected power and goes down with every outage —
  collected superblock errors after each cut: fixed by fsck on 2026-08-22,
  broken again on 2026-08-30, 17 errors by the morning of 2026-09-03, `ls`
  returning "Structure needs cleaning". `fsck-userdata.sh` v2 (in
  `board-config/scripts/`, deployed to `/home/forlinx/`) now does the whole
  thing in one stop of ~100 s: e2fsck, `tune2fs -O has_journal -e remount-ro
  -c 20`, fstab `defaults,errors=remount-ro,nofail,x-systemd.device-timeout=30
  0 2`, remount, restart. What that buys on the next power cut: the journal
  replays on mount instead of leaving holes; `pass 2` lets systemd-fsck fix
  small things in preen mode before mounting; if it cannot, `nofail` still
  boots the board (SSH works) while HA stays down because of
  `Requires=userdata.mount` — then run the script by hand; and if an error
  appears while running, the partition goes read-only instead of corrupting
  further, which HA reports as write failures and `health` as
  `fs_state`. `cli.py health` reports `fs_state` / `fs_error_count` /
  `fs_journal`; `fs_journal=0` is a problem again.
- Active swap is `/dev/zram0`, 1 GiB compressed RAM swap. The old 4 GiB eMMC
  swapfile was removed.
- Use `du -x` on `/userdata`. The photo library is mounted outside the HA
  configuration tree at `/mnt/homemate_media/foto`; `config/media/foto` is a
  symlink to it so backups do not traverse NAS media.
- Journald is currently capped by `SystemMaxUse=50M`. NAS synchronization is
  the durable log/config path; do not silently raise the cap without checking
  free root space.

### `/userdata` is only 2.5 GB and it has already filled up once

On 2026-08-09 the partition hit 100% and Home Assistant entered a restart loop:
it could not even create its lock file and died with
`OSError: [Errno 28] No space left on device`, eleven times in a row. Nothing
in the UI explains this — the service reports `activating (auto-restart)` and
the HTTP port never opens.

What consumed the space:

- `home-assistant.log` — **74 MB**, because `tuya_sharing: debug` had been left
  on since 2026-08-05 and logs every cloud MQTT packet, several per second;
- `home-assistant_v2.db` **894 MB** plus `home-assistant_v2.db-wal` **571 MB**.
  The WAL is the trap: it grows separately from the database, and an unclean
  shutdown leaves it behind.

Recovery sequence that worked, in this order:

1. Truncate the log, keeping a tail for diagnosis
   (`tail -n 3000 … > /tmp/x && cat /tmp/x > home-assistant.log`), delete
   `home-assistant.log.1`. Frees tens of MB — enough for the next step.
2. Stop Home Assistant, then checkpoint the WAL into the database:
   `python -c "import sqlite3; sqlite3.connect(PATH, timeout=60).execute('PRAGMA wal_checkpoint(TRUNCATE)')"`.
   This freed 571 MB while the database itself grew only ~20 MB. Never delete
   `-wal` or `-shm` by hand — that risks the database.
3. Remove the cause before starting again, otherwise the log refills within days.

Prevention: keep debug logging strictly temporary and prefer a narrower logger
target; watch `df -h /userdata` whenever the database is near 1.5 GB, since
`purge_keep_days` alone does not bound the WAL.

## Recorder retention (2026-09-03)

`purge_keep_days: 21`, `auto_repack: false`, ~65 MB/day after the second
exclude batch in `configuration.yaml` (Deye duplicates «Load UPS»/«Internal
CT»/«Output»/«Power Losses»/external CT, `inverter_connection` and
`inverter_update_interval` attribute churn, Sonoff gate voltages, cloud
duplicates of local `_2` meter/plug entities). Measured before the cut:
3.87 M `states` rows per 7.3 days, 1.24 GB file with 385 MB free pages,
~110 MB/day of real data. 21 days ≈ 1.4 GB on the 2.4 GB partition; the
`/userdata` free-space watchdog (250 MB) is the safety net - fall back to 14
if it fires. Repack is off because VACUUM needs a full copy of the file.
Next reserve if more depth is wanted: Deye poll interval 5 → 10 s (~-25 %),
or an external database - not SQLite on NFS. Excluding an entity also stops
its long-term statistics; nothing in the batch has a kWh unit, so the Energy
panel is unaffected. Recorder settings apply only after an HA restart.

## Backup meaning and location

In this project, **backup** means a copy stored outside the MB35x8 board on the
CloudMate QNAP NAS. The canonical destination is:

- SMB share: `//192.168.50.25/HomeAssistant`
- NAS folder: `MB35x8/backups`
- Windows view: `\\CloudMate\HomeAssistant\MB35x8\backups`

It does **not** mean a persistent archive under
`/userdata/hass/config/backups`, `/userdata`, `/home/forlinx`, or any other
board filesystem. Do not stage full HA `.tar`/`.tar.gz` archives on eMMC and
then upload them: the 2.5 GiB `/userdata` partition cannot safely hold them.

Before reporting a backup as successful, verify the remote file exists on the
NAS and that its byte size matches the source/result. A local file may be
deleted only after that verification. Never read or expose the archive
contents, `.storage`, the recorder database, or credentials while verifying.

Distinguish a **deployment rollback copy** from a Home Assistant backup. Before
overwriting one small configuration or systemd file, prefer a timestamped copy
on the NAS. If that is temporarily impossible, a short-lived copy under `/tmp`
is acceptable only for the duration of the atomic deployment; remove it after
validation. Never retain rollback copies in `/userdata`.

Current state since 2026-08-06: QNAP exports
`/HomeAssistant/MB35x8/backups` over NFS only to `192.168.50.141`. The board
mounts it directly at `/userdata/hass/config/backups` with
`userdata-hass-config-backups.mount`; `homemate-ha-backups-mount.timer` retries
the mount every five minutes. The underlying local directory is root-owned and
mode `0555`, so HA fails closed instead of writing backup archives to eMMC when
NAS is unavailable. In the HA UI, `This system` therefore means this NAS mount,
not board storage.

Automatic backups run daily at HA's system-optimal time (currently about 04:46),
retain seven copies, include HA settings, exclude recorder history, and write
directly to NAS. The 2026-08-06 acceptance backup was 49,960,960 bytes; `/userdata`
stayed at 54% used and HA held no photo-album files open. Never move the photo
mount back under the configuration tree as a real mount: Core backups archive
the whole config tree and would recursively include the NAS photo library.

## Enabled supporting services

- `homemate-nas-sync.timer`: hourly incremental journal export to NAS. It does
  not create, stage, or upload Home Assistant backup archives from the board.
- `userdata-hass-config-backups.mount` plus
  `homemate-ha-backups-mount.timer`: direct NAS-only HA backup destination.
- `house-analyst.timer`: scheduled local analysis.
- `zram-swap.service`: compressed swap.
- `wyoming-vosk.service`: local speech-to-text when enabled/configured.
- `mnt-homemate_media-foto.mount`: read-only photo library outside the backup
  tree. The video NFS unit remains disabled until the QNAP video share is
  explicitly exported read/write to the board.

## Architecture limits

The Forlinx kernel has no `CONFIG_OVERLAY_FS`, `CONFIG_VETH`, `CONFIG_MEMCG`, or
`CONFIG_CGROUP_PIDS`. Docker/HA OS/Supervised are not viable on this image.
Changing that requires a validated vendor kernel/image and a separately planned
reflash. Do not experiment on the production board.

## Secrets boundary

Never put `.storage`, `secrets.yaml`, the recorder database, NAS credentials,
access tokens, private keys, or device local keys in Git or MCP output.
