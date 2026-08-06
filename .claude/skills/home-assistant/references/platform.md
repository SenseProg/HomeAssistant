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
- Use `du -x` on `/userdata`. The photo library is mounted outside the HA
  configuration tree at `/mnt/homemate_media/foto`; `config/media/foto` is a
  symlink to it so backups do not traverse NAS media.
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
