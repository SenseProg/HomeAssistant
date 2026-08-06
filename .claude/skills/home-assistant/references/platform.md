# Platform and services

## Runtime

- Board: MB35x8 v1.0 carrier with Forlinx RK3568J SoM.
- OS: Ubuntu 20.04.6 LTS, kernel 4.19.206, aarch64, 4 cores, 3.8 GiB RAM.
- Host/IP: `ok3568`, `192.168.50.141` on `eth1`.
- Home Assistant: Core 2026.7.4 in `/home/forlinx/hass-venv-314` using
  Python 3.14.6.
- Config: `/userdata/hass/config`.
- Service: `home-assistant.service`.
- HA timezone: `Europe/Kyiv`; board OS timezone: `Asia/Shanghai`.

## Storage and memory

- The root filesystem contains the venv and Node/Claude tooling.
- `/userdata` contains HA config and recorder data.
- Active swap is `/dev/zram0`, 1 GiB compressed RAM swap. The old 4 GiB eMMC
  swapfile was removed.
- Use `du -x` on `/userdata`; `media/foto` and `media/video` may be NAS mounts.
- Journald is currently capped by `SystemMaxUse=50M`. NAS synchronization is
  the durable log/config path; do not silently raise the cap without checking
  free root space.

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

Current state since 2026-08-06: HA automatic backups are set to `Never` and the
local location `This system` is disabled. Existing encrypted backups and the
older Smart Irrigation archives were verified and moved to
`MB35x8/backups`; `/userdata/hass/config/backups` is empty. Re-enable automatic
backups only after an NFS/SFTP remote backup location is configured and a test
proves that the archive is written directly to NAS without consuming eMMC.

## Enabled supporting services

- `homemate-nas-sync.timer`: hourly incremental journal export to NAS. It does
  not create, stage, or upload Home Assistant backup archives from the board.
- `house-analyst.timer`: scheduled local analysis.
- `zram-swap.service`: compressed swap.
- `wyoming-vosk.service`: local speech-to-text when enabled/configured.
- NFS mount units for photo and video media.

## Architecture limits

The Forlinx kernel has no `CONFIG_OVERLAY_FS`, `CONFIG_VETH`, `CONFIG_MEMCG`, or
`CONFIG_CGROUP_PIDS`. Docker/HA OS/Supervised are not viable on this image.
Changing that requires a validated vendor kernel/image and a separately planned
reflash. Do not experiment on the production board.

## Secrets boundary

Never put `.storage`, `secrets.yaml`, the recorder database, NAS credentials,
access tokens, private keys, or device local keys in Git or MCP output.
