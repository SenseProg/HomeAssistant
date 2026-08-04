# MB35x8 Home Assistant operations

## Remote access

The board already runs ZeroTier, but is not joined to a network. Use a private
ZeroTier network rather than exposing TCP 8123 or SSH directly to the internet.
After joining, authorize node `46faf402eb` in ZeroTier Central, restrict routes
to the Home Assistant host, and verify both SSH and `http://<zerotier-ip>:8123`.
Only then disable SSH password authentication.

## Network topology and presence

`ASUS RT-AX55` (`192.168.50.1`) is the main router, DHCP server and the source
of the `asuswrt` device trackers. Its primary Wi-Fi network is `Отаке`.
`Tenda AC10 v3` (`192.168.50.2`) is an access point for SSID `Промінь`, while
`Tenda A9` (`192.168.50.102`) repeats `Отаке`. All three devices bridge the same
`192.168.50.0/24` LAN.

The Network dashboard correlates each active ASUS tracker MAC with the live
client lists reported by both Tenda devices. It labels the current connection as
direct ASUS/`Отаке`, Tenda AC10/`Промінь`, or the Tenda A9 repeater. A device
absent from both Tenda lists but present in ASUS is classified as a direct ASUS
client. For example, Galaxy J8 (`192.168.50.56`) currently follows the direct
ASUS path, while grandmother Sima's Galaxy S21 (`192.168.50.74`) is connected
through Tenda AC10/`Промінь`.

Presence is person-based, not access-point-based. `person.dim_kovtuni` is
displayed as Дмитро and combines his mobile-app GPS and ASUS S23 tracker. The
storage person `person.babusia_sima` uses
`device_tracker.s21_pol_zovatela_kateryna`. Therefore moving between `Отаке`,
`Промінь`, and the repeater does not make a person disappear from the home list.

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
Open-Meteo data, collection every 30 minutes, a daily calculation at 19:55, a 2 mm
forecast-precipitation skip threshold, and observed-watering feedback. Direct
valve control in Smart Irrigation must remain disabled so that only Irrigation
Unlimited owns the actuators.

Create Smart Irrigation zones only for physical irrigation zones 1 and 2. Both
commissioned zones use 250 m², 40 L/min, module `0: PyETO`, and sensor group
`0: Група датчиків за замовчуванням`. Keep Smart Irrigation direct valve control
disabled and map observed watering to `switch.avtopoliv_kontroler_switch_1` and
`switch.avtopoliv_kontroler_switch_2`. The existing weekday automation remains
the only start source and runs 30 minutes before sunrise on enabled weekdays. It reads
`sensor.smart_irrigation_zona1` and `sensor.smart_irrigation_zona2`, then
queues the calculated durations on the corresponding Irrigation Unlimited zone
entities. Until a Smart zone exists, that zone safely falls back to its current
`input_number.poliv_zona_*_hvylyn` duration; a calculated value of zero skips
the zone. Smart Irrigation itself does not operate the valves: the weekday
automation starts Irrigation Unlimited, which owns the safe valve/pump
sequence. Zone 3 remains manual and is not part of weather-driven calculation.

The duration formula is `abs(water deficit in mm) / precipitation rate × 3600`,
where precipitation rate is `throughput × 60 / area`. At the commissioned
250 m² and 40 L/min this is 9.6 mm/h: a 4 mm deficit produces 1500 seconds
(25 minutes), while a freshly collected 0.05 mm deficit produces only about
19 seconds. Module `1: Static` is kept as an optional fixed-reference module
with delta `-4 mm`; the production zones remain on PyETO so weather and rain
affect the result.

Practical Smart Irrigation field settings for this installation:

- `Size` is the actual irrigated area (250 m² per commissioned zone), while
  `Throughput` is the combined flow of that zone's sprinklers (currently
  40 L/min), not the pump's nameplate capacity.
- `Bucket` is the accumulated soil-water balance: negative means a deficit and
  positive means stored water. `Maximum bucket` caps only the positive stored
  amount; water above it is treated as runoff. It does not cap a deficit.
- `Drainage rate` applies only when the bucket is positive. The current
  50.8 mm/h is a provisional default pending a soil-type or field test.
- `Lead time` is unconditional extra runtime added after the calculated limit,
  intended only for filling pipes or building pressure; keep it at 0 seconds.
- The optional cumulative volume meter must be a physical `total_increasing`
  water-meter total in L or m³. Until one is installed, leave it empty: observed
  watering already credits 40 L/min multiplied by the real valve runtime.
- PyETO `Coastal` remains off for this inland site. `Forecast days` is explicitly
  0 so the calculation uses the day's measured data instead of averaging future
  forecast days. Sensor group 0 supplies all nine inputs from Open-Meteo to both
  zones; add another group only for a separate local weather station or
  microclimate.

Automatic irrigation must remain disabled until the physical values and a dry
commissioning test have been completed. The pinned custom components can be
reinstalled or upgraded reproducibly with
`board-config/scripts/homemate-install-irrigation-components.sh`.

### Ukrainian localization

The Home Assistant user profile language is Ukrainian. Smart Irrigation's
upstream Ukrainian catalogue translates the panel content, while the upstream
sidebar and panel title are fixed to the English product name. HomeMate applies
a small display-only overlay that changes those visible strings to
`Розумний полив` and translates the remaining terms `водний баланс ґрунту`,
`добова зміна водного балансу`, and `добовий дефіцит евапотранспірації`; the
integration domain, service names, entity IDs and device
identity stay unchanged. Reapply it after a manual HACS update with:

```bash
/userdata/hass/config/scripts/homemate-localize-smart-irrigation-uk.sh
```

The pinned component installer applies the same overlay automatically.
Component backups are kept under `/userdata/hass/backups/custom_components`,
outside the live `custom_components` directory, so Home Assistant cannot mistake
a backup for an importable integration.

## Blauberg room recuperators

The PRANA RECUPERATOR 150 (`2 floor` integration device) is physically installed
in `Спальня батьків`. The complete PRANA device is assigned to that Home
Assistant area, so its supply/extract fans, operating modes, air-quality sensors
and temperature sensors are available together on the room page. Its full
control and monitoring cards also remain on the dedicated `Вентиляція` dashboard.

The two Blauberg/Siku room recuperators are connected directly over the local
UDP protocol; no vendor cloud is involved. Home Assistant uses the pinned
`Siku (Blauberg) Fan` custom integration `2.2.6` at upstream commit
`589b266f5464701c218af554ede135d9edf333e2`. Reinstall or reproduce it with:

```bash
/home/forlinx/homemate-scripts/homemate-install-siku.sh
```

The repository copy is
`board-config/scripts/homemate-install-siku.sh`; it verifies the upstream
archive SHA-256, compiles the component, backs up any replaced component under
`/userdata/hass/backups/custom_components`, and runs `check_config`.

Current local units:

| Dashboard name | Address | MAC | Physical room |
|---|---|---|---|
| Blauberg №1 | `192.168.50.27:4000/UDP` | `98:F4:AB:EE:A5:C5` | Кімната хлопців |
| Blauberg №2 | `192.168.50.123:4000/UDP` | `98:F4:AB:EE:A8:4E` | Кімната Олесі |

Each dashboard card exposes power, three speed levels, automatic/manual/on,
party and sleep presets, airflow direction and alternating direction. It also
shows humidity, RPM, alarms, filter/timer countdowns and firmware. The filter
alarm reset button is intentionally omitted from the main dashboard; use it
only after physical filter service.

The physical mapping was confirmed on 2026-08-05: unit №1 (`.27`) belongs to
`Кімната хлопців`, and unit №2 (`.123`) belongs to `Кімната Олесі`. The Home
Assistant device registry uses these same areas. Configuration entry credentials
remain only in Home Assistant storage and are never written to Git.
