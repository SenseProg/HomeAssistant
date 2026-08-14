# Second board — running the house since 2026-08-13

This directory holds the files that differ on the second MB35x8 board. Since
`2026-08-13 14:44` that board *is* the house: `switch-mode.sh standalone` was
run, and Home Assistant on the original board stays `disabled`.

Everything below was measured on the board, not assumed.

## Addresses: the order in netplan is load-bearing

`netplan-01-netcfg.yaml` gives `eth0` two addresses:

```
addresses: [192.168.50.141/24, 192.168.50.168/24]
```

`.141` **must stay first**. The NAS exports both of its shares to
`192.168.50.141` and to nothing else (`showmount -e 192.168.50.25`), and Linux
uses the *first* address of a subnet as the source for outgoing traffic. On
2026-08-14 the board briefly held `.141` as a secondary address behind `.168`
and every NFS mount was still refused — the address was present, but the
requests left with the wrong source:

```
ip route get 192.168.50.25   ->   src 192.168.50.168
```

`.168` is kept as a second address on purpose. This SoM has no usable debug
UART, so a wrong `.141` would mean a trip to the board with a monitor and a
keyboard. With both configured, a mistake in one still leaves a way in.

Note that `switch-mode.sh` writes a *single* address. Re-running it restores
`.141` alone — mounts keep working, the `.168` lifeline does not.

## Mount units cannot point through `config`

`switch-mode.sh` makes `/userdata/hass/config` a symlink to `config-standalone`
or `config-mirror`. systemd refuses any mount whose path contains a symlink:

```
Mount path /userdata/hass/config/media/video is not canonical (contains a symlink).
Failed to run 'mount' task: Too many levels of symbolic links
```

So in standalone mode three of the five mounts — camera archive, NAS backups and
the `www` bind that exposes clips at `/local` — could never come up. The units
here mount on the canonical `config-standalone` paths instead. Home Assistant
still finds everything at its usual `/userdata/hass/config/...` paths, because
the symlink resolves to exactly those directories.

`nas-mounts.service` names its mount points by **path**, never by unit name, and
must keep doing so: the real filenames on the board contain systemd escapes that
do not survive a trip through a shell. The files in `systemd/` are stored here
with readable names; on the board they are:

| stored here | real filename on the board |
| --- | --- |
| `userdata-hass-config-standalone-media-video.mount` | `userdata-hass-config\x2dstandalone-media-video.mount` |
| `userdata-hass-config-standalone-backups.mount` | `userdata-hass-config\x2dstandalone-backups.mount` |
| `userdata-hass-config-standalone-www-motion-clips.mount` | `userdata-hass-config\x2dstandalone-www-motion\x2dclips.mount` |

Generate the correct name with `systemd-escape -p --suffix=mount <path>` rather
than typing it.

If the board is ever switched back to mirror mode, these three paths must follow
to `config-mirror`, in the units and in `nas-mounts.service` alike.

## `netplan-fallback` watches a different interface here

The shared `board-config/systemd/netplan-fallback.service` checks `eth1`, which
is correct on the original board — that is where its LAN is. On this board the
LAN is `eth0` and `eth1` is permanently `NO-CARRIER`, so the condition "no IPv4
after 45 s" was true on *every* boot. The parachute silently restored the
pre-migration config and ran `netplan apply`, undoing the move each time the
board started. It also wiped an address added by hand roughly three minutes
after it was set.

The copy here watches `eth0`. `/root/netcfg.bak.yaml`, the file it restores, was
updated on the board to the post-migration config as well, so even a genuine
fallback no longer reverts the migration.

## Storage layout after the move

The root partition was full at 99% with 175 MB free, so the 1.2 GB Home
Assistant venv had been placed on `/userdata`, leaving too little room for the
database. It now lives at `/home/forlinx/hass-venv` with
`/userdata/hass/venv` as a symlink to it — the venv's shebangs are absolute
(`#!/userdata/hass/venv/bin/python`), and the symlink keeps all 86 379 files
working without rewriting any of them.

That freed `/userdata` for the database: 2.0 GB against measured growth of
130 MB/day, so `purge_keep_days: 7` fits at roughly 0.9 GB. The three-day value
was forced by the old cramped partition and is no longer needed.

`logrotate-matebox` belongs at `/etc/logrotate.d/matebox`. The Aquamate
emulator logs one `dutyCycle: START` line three times a second with no rotation
of its own; the file had reached 450 MB. It needs `su forlinx forlinx` because
logrotate refuses a directory that is group-writable by anyone but root.

## What is not in this directory

`f_emul.service` and `a_emul.service` — the Freezemate and Aquamate Qt
emulators — run from `/home/forlinx/matebox` on this board and are `enabled` and
active. They are not part of the house, but they are not abandoned either, and
`/opt/qt6.8.1` cannot be removed while they run: both link against it.
