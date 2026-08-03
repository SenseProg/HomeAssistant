# MB35x8 Home Assistant operations

## Remote access

The board already runs ZeroTier, but is not joined to a network. Use a private
ZeroTier network rather than exposing TCP 8123 or SSH directly to the internet.
After joining, authorize node `46faf402eb` in ZeroTier Central, restrict routes
to the Home Assistant host, and verify both SSH and `http://<zerotier-ip>:8123`.
Only then disable SSH password authentication.

## NAS backup and journal archive

The NAS is `CloudMate` (`192.168.50.25`), share `HomeAssistant`. The dedicated
account `homeassistant-backup` has read/write permission only to that share and
only the Microsoft Networking application privilege.
Credentials are stored only on the board in `/etc/samba/credentials/homeassistant-backup`
with mode `600`; they must never be committed.

The Forlinx 4.19 kernel lacks both CIFS and autofs support. NAS transfer therefore
uses `/usr/bin/smbclient` in userspace with the root-only credential file
`/etc/samba/credentials/homeassistant-backup`; no NAS filesystem is mounted.

`homemate-nas-sync.timer` runs hourly. It uploads any new encrypted HA backup
archives and journal entries since the last successful transfer. The journal
cursor advances only after the compressed log reaches the NAS. NAS retention
and off-site synchronization are configured on CloudMate; the board never
deletes NAS data automatically.

## Recovery layers

1. Git contains declarative YAML, systemd units, and operational scripts.
2. Home Assistant creates a full encrypted backup every day and keeps three on
   the board.
3. The NAS receives those encrypted archives plus incremental system journals.
4. CloudMate must replicate `HomeAssistant/MB35x8` off-site to complete 3-2-1.

Keep the Home Assistant emergency kit separately from both the board and NAS.

The first NAS transfer was verified byte-for-byte with SHA-256 on 2026-08-03.
CloudMate is a separate device but remains in the same building; an HBS cloud or
second-site replication target is still required for a literal off-site copy.

## NAS photo library

CloudMate exports `/Фотоальбом` over NFSv4 only to the board address
`192.168.50.141`. The export is read-only and uses `Squash no users`; the
read-only export permission remains the write-protection boundary while keeping
the existing NAS file ownership readable by the Home Assistant process.

The board mounts the export at `/userdata/hass/config/media/foto` with
`userdata-hass-config-media-foto.mount`. The unit uses `ro,soft,timeo=100`, so a
NAS outage cannot leave Home Assistant indefinitely blocked on a hard NFS
mount. Do not add a duplicate entry to `/etc/fstab`.

Verify the path and mount with:

```sh
showmount -e 192.168.50.25
findmnt -T /userdata/hass/config/media/foto
systemctl is-active userdata-hass-config-media-foto.mount
```

Home Assistant exposes the mounted tree automatically as
`Media > My media > foto`; no `configuration.yaml` entry is required.

## Known platform limitations

- The vendor package database lacks list/md5 metadata for many base packages.
  An unfinished FFmpeg/TIFF transaction and its conflicting
  `libturbojpeg0-dev` package were repaired, but mass-reinstalling the base OS in
  place is unsafe. Resolve this with a tested vendor reflash/migration image.
- The kernel lacks CIFS, autofs, overlayfs, veth, bridge, and required cgroups.
  `smbclient` handles NAS transfer; Docker and systemd automount are unavailable.
- `Terneo 2` (`192.168.50.157`) and the failed RT-AX55 UPnP entry are disabled
  in Home Assistant until the physical thermostat or integration is needed.
- Official Tuya still needs user reauthentication. LocalTuya remains active for
  the locally controlled devices.

## Platform migration

The current vendor kernel 4.19.206 lacks overlayfs, veth, bridge, memory cgroups,
and cgroup pids, so it cannot host a normal Home Assistant Container. Home
Assistant OS has no supported image for this custom MB35x8 carrier/RK3568J.

Preferred paths, in order:

1. Obtain an official Forlinx Ubuntu 22.04 or Linux 5.10 image for the exact SoM
   and carrier, then verify the required container kernel options on spare media
   or a second board before touching production eMMC.
2. If the vendor image supports Docker, restore an encrypted HA backup into Home
   Assistant Container and test every custom integration before cut-over.
3. Otherwise move Home Assistant to a supported HA OS host and retain MB35x8 as
   an edge controller/gateway.

Never in-place `do-release-upgrade` this vendor image and never flash production
without a tested full-device recovery image and serial-console access.

## Smart irrigation

Irrigation Unlimited `2025.12.0` is the hardware execution layer. Its YAML
controller opens a zone valve three seconds before the pump and stops the pump
three seconds before closing the final valve. It has no schedule of its own;
all automatic starts are additionally gated by
`input_boolean.poliv_avtomatika_dozvolena`.

Smart Irrigation `v2026.7.1` is the calculation layer. It uses keyless
Open-Meteo data, hourly collection, a daily calculation at 23:00, a 2 mm
forecast-precipitation skip threshold, and observed-watering feedback. Direct
valve control in Smart Irrigation must remain disabled so that only Irrigation
Unlimited owns the actuators.

Before adding the three Smart Irrigation zones, measure or confirm both the
irrigated area in square metres and the real flow in litres per minute for each
zone. Automatic irrigation must remain disabled until these values and a dry
commissioning test have been completed. The pinned custom components can be
reinstalled or upgraded reproducibly with
`board-config/scripts/homemate-install-irrigation-components.sh`.
