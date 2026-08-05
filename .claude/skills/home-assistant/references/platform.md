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

## Enabled supporting services

- `homemate-nas-sync.timer`: hourly NAS synchronization.
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
