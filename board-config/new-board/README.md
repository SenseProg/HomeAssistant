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

## `mirror-alias-ip.service` is disabled, and must stay that way

That unit exists on the board and adds `192.168.50.142/24` to `eth0`. It dates
from when this board was a stand on DHCP whose lease kept moving; its own
comment says "the main address still comes from the router", which stopped
being true when the board took a static one.

On 2026-08-14 it added `.142` back and `.142` ended up *primary*, ahead of the
netplan addresses. Every NFS mount dropped within minutes, because outgoing
traffic to the NAS then left as `.142`:

```
ip route get 192.168.50.25   ->   src 192.168.50.142
```

It is now `disabled`. Note that `systemctl stop` alone does not remove the
address — the unit is `RemainAfterExit=yes` with no `ExecStop`. Use
`netplan apply` to flush it and restore the configured order.

This is the same class of fault as `netplan-fallback` above: a unit that
quietly redefines the network on top of netplan. When something on this board
loses its address or picks a surprising one, look for a unit before suspecting
the router.

## The camera sits in a segment this board cannot reach

Measured 2026-08-14. From this board, `192.168.50.2` (Tenda AC10), `.175` and
`.201` (the Hikvision camera) answered **0 of 10** pings, while the NAS on the
same interface answered 10 of 10. The spare board reached all three. It is not
the cable — `rx_errors` and `rx_crc_errors` are both `0` — and it is not ARP: a
static neighbour entry with the camera's real MAC changed nothing, so the
traffic is dropped below IP. The board's cable goes to a segment that does not
bridge to theirs.

Until the cable moves, the workaround has two halves. On the spare board,
`camera-relay.service` (in `board-config/systemd/`) forwards and masquerades —
masquerading is not optional, because with plain forwarding the camera would
answer `192.168.50.141` directly and the reply would die in the same isolated
segment. On this board, the three host routes live in the `routes:` block of
`netplan-01-netcfg.yaml`, and `sysctl-99-isolated-hosts.conf` keeps
`accept_redirects` off so the relay cannot be told to hand the path back.

The routes were first written as a oneshot unit, and that was wrong. `eth0`
lost carrier at 14:13 and again at 14:32 on 2026-08-14; each time networkd
re-configured the link and flushed every route it did not own, and the unit
never re-ran, because `RemainAfterExit=yes` left systemd believing it was still
active. The camera went unreachable again with the service still reporting
`active`. Anything that must survive this board's link flapping belongs in
netplan, not in a oneshot unit.

Note when retiring the workaround: nothing on this side needs stopping — remove
the `routes:` block and re-apply. On the spare board `camera-relay.service` has
an `ExecStop`, so `systemctl disable --now` reverts it cleanly. Retire both once
this board is plugged into a port that reaches that segment; that also ends the
house's dependency on the spare board staying powered on.

## Remote access: Tailscale, and a public Cloudflare tunnel

Two paths exist on this board, and they are not equivalent.

**Tailscale** is the private one. `tailscaled` must run with
`--tun=userspace-networking` (`default-tailscaled` here) because this kernel
has no `CONFIG_TUN` and no `/dev/net/tun` — the same reason WireGuard cannot be
used at all. The node is `ok3568-house` on the `roman.d.kovtun@gmail.com`
tailnet. Note that in userspace mode the board cannot reach its own `100.x`
address; only peers can, so testing from the board itself will always look
broken.

Serve is not enabled on that tailnet yet, so there is no `https://…ts.net`
hostname and Home Assistant has to be reached as
`http://<tailscale-ip>:8123` — with the port. A phone opening the address
without it lands on port 80, where nothing listens; the daemon log shows
exactly that: `could not connect to local backend server at 127.0.0.1:80`.

**The Cloudflare named tunnel** is the public one, on `sonyachny.pp.ua`
(registered at NIC.UA, delegated to Cloudflare on 2026-08-17).
`cloudflared-ha.service` runs tunnel `ha-house` with the ingress rules in
`cloudflared-config.yml`: `ha.sonyachny.pp.ua` reaches Home Assistant, and
anything else that arrives at the tunnel gets a 404 rather than being quietly
forwarded. It registers four connections — two through Kyiv, two through
Frankfurt — and opens no port on the router.

The credentials (`~/.cloudflared/cert.pem` and the tunnel's `<uuid>.json`) stay
on the board and are deliberately not in this repository. To rebuild the tunnel
elsewhere, run `cloudflared tunnel login` again; the config here is enough to
describe what it should serve.

It replaced `cloudflared-quick.service`, kept here for reference, which needed
no account but was issued a **new random `trycloudflare.com` hostname on every
start**. Its wrapper published the current one to
`/userdata/hass/config/www/cloudflare-url.txt` (`/local/cloudflare-url.txt` from
a phone) precisely because the address died at each reboot. That file now holds
the fixed hostname instead.

Understand what a public tunnel means here: this Home Assistant opens
irrigation valves and starts a pump. Until Cloudflare Access is configured in
front of it, the only barriers are the HA login page and
`login_attempts_threshold: 5` — enable two-factor authentication on the HA
accounts. `systemctl disable --now cloudflared-ha` removes the exposure
completely.

One trap worth writing down: a tunnel's DNS record must be **proxied** (orange
cloud). It resolves to `<uuid>.cfargotunnel.com`, which has no public address of
its own and only works through Cloudflare's network. While the zone was still
`Pending`, Cloudflare served that CNAME unproxied, so the hostname resolved to
`fd10:aec2:5dae::` — a private address — and nothing connected. The record was
already marked Proxied in the dashboard; proxying simply is not applied until
the zone goes Active.

## What is not in this directory

`f_emul.service` and `a_emul.service` — the Freezemate and Aquamate Qt
emulators — run from `/home/forlinx/matebox` on this board and are `enabled` and
active. They are not part of the house, but they are not abandoned either, and
`/opt/qt6.8.1` cannot be removed while they run: both link against it.

## The clip archive stopped at the minute of the move, and why

No motion clip was written between `2026-08-13 14:40` — the minute Home
Assistant was disabled on the original board — and 2026-08-17. Two separate
faults, both created by the move itself:

**`allowlist_external_dirs` was compared against the wrong paths.** Home
Assistant resolves a requested file path to its real location before checking
it, but compares the allowlist entries exactly as written. `switch-mode.sh`
makes `/userdata/hass/config` a symlink, so a clip aimed at
`/userdata/hass/config/media/video/...` became
`/userdata/hass/config-standalone/media/video/...` and matched nothing —
`Can't write ..., no access to path!` on a directory that was, on paper,
allowed. On the original board `config` was a real directory and the paths
matched, which is why it had always worked. The allowlist now carries the
canonical `config-standalone` paths; the old forms are kept as well, harmlessly.

**The gallery rebuild pointed at the other board's interpreter.**
`shell_command.rebuild_clip_gallery` invoked
`/home/forlinx/hass-venv-314/bin/python`, which exists only on the original
board, so it failed silently on every motion event. It now uses
`/userdata/hass/venv/bin/python`. Rebuilt by hand afterwards: 7 days, 2207
clips.

Note that `pyhik` does not recover on its own. After the camera has been
unreachable for a while its retry interval grows — 154 consecutive failures had
pushed it to 775 s between attempts — and it will not reconnect promptly even
once the camera answers again. Restart Home Assistant after restoring the path
to the camera, or the entities stay `unavailable` for a quarter of an hour.

## The relay is still required: measured again on 2026-08-18

After the house board's cable was moved, its link improved from 10 Mb/s to
100 Mb/s, so something physical did change. The segmentation did not. With the
three relay routes removed, `192.168.50.201`, `.2` and `.175` answered **0 of
4** pings and the camera's ARP entry stayed `INCOMPLETE` — no reply at layer 2
at all — while the NAS on the same interface was unaffected. The routes were
restored immediately.

So the spare board must stay powered for the camera to work. The remaining test
is to give the house board the exact cable and port the spare board uses, rather
than a different port; failing that, its unused `eth1` is worth trying.

## Two Home Assistants ran at once on 2026-08-18, briefly

The house board dropped off the network on 2026-08-17 19:08 and stayed dark for
seventeen hours. It had not crashed — uptime showed it had been running the
whole time — only its link was gone. Home Assistant was started on the spare
board to keep the house working, and `ha.sonyachny.pp.ua` was repointed to a
second tunnel there (`ha-spare`, kept in this repository for reference).

When the house board's link returned, its own Home Assistant was still enabled
and active, so for a while both boards held LocalTuya sessions to the same
valves and pump — the one failure mode the handover notes call out as able to
break something physical. Nothing was actuated in that window. The duplicate was
stopped, the DNS record was repointed back at `ha-house`, and the spare board's
tunnel was disabled.

Home Assistant on the spare board is deliberately left `disabled` at boot. If it
is ever started again as a stand-in, check first that the house board is not
answering on `.141` or `.168`.

## The relay is gone: it was the cable all along, 2026-08-18

Swapping the two boards' Ethernet cables end for end — the same cable and port
the spare board had been using, not merely a different port — gave this board
direct access to the segment it had never reached. With all three relay routes
removed, the camera answered **4 of 4** and its ARP entry resolved to the real
MAC `10:12:fb:f7:95:ad`, `REACHABLE`. Simply moving the cable to another port a
day earlier had raised the link from 10 Mb/s to 100 Mb/s but changed nothing
about what was reachable, which is what made the cable itself the suspect.

The `routes:` block is out of `netplan-01-netcfg.yaml`, `camera-relay.service`
is retired, and the files for the spare board are removed from this repository
because that board has left the site. `sysctl-99-isolated-hosts.conf` stays: it
only turns off `accept_redirects`, which is harmless and mildly safer.

There is no fallback board any more. Tailscale on this board is the only
independent way in if the tunnel or the LAN address misbehaves — treat it as
part of the system, not a convenience.

## `external_url` was never set

The companion app had not contacted this instance in two days, and push
notifications had nowhere to return to: `external_url` was `None` while
`internal_url` pointed at `http://192.168.50.141:8123`. Both are now in
`configuration.yaml` — `external_url` is the tunnel hostname, since nothing is
forwarded on the router and that is the only way in from outside.

Two phones are registered as companion apps: `SM-S918B` and `M2006C3MNG` — the
latter is a Redmi 9C NFC, which is worth writing down because Home Assistant
names its 93 entities after the model code, so searching the registry for
"redmi" finds nothing.

## Do not run `tailscale login` to repair a session

On 2026-08-19 the node was found logged out with `invalid key: API key does not
exist` — the second time. Restarting `tailscaled` restored it from the stored
credentials. Running `tailscale login` afterwards, to be thorough, forced a
fresh authentication and threw the working session away; recovering it needed
`sudo tailscale switch <id>`, since the profile was still on disk.

Check `sudo tailscale switch --list` first. And the underlying cause is still
open: `key expires: 2027-02-10`. Disable key expiry on `ok3568-house` in the
admin console — it cannot be done from the CLI, and until it is, the node will
fall out of the tailnet again on its own.

## A dead RTC took the Tuya integration down for weeks

All 37 entities of the official `tuya` integration were `unavailable`, and a
re-authentication done in the app changed nothing. The integration was not the
fault. The chain, in order:

The RTC cannot be read at all — `timedatectl` answers `Failed to read RTC:
Invalid argument`, the battery is dead — so every boot starts from whatever the
clock happens to hold. `systemd-timesyncd` should correct that, but on
2026-08-20 it was found `enabled / inactive`: at boot it had logged `No network
connectivity`, then timed out against `ntp.ubuntu.com`, and never came back.
The clock was sitting in **June 2024**.

Nothing looked broken until TLS did. Tuya's certificate is valid from
`Aug 20 2025` to `Sep 10 2026`, so to a board living in 2024 it was *not yet
valid*:

```
SSLError: certificate verify failed: certificate is not yet valid
```

No request ever reached Tuya, which is why the token could not be refreshed and
why re-authentication could not possibly succeed — the QR was genuine, the
board simply could not talk to the server behind it. After the clock was
corrected the error changed to `(1010) token is expired`, which is Tuya
answering rather than the connection failing, and the re-auth then worked
first try.

`timesync-retry.service`/`.timer` is the guard: it checks 90 s after boot and
every ten minutes after that, and restarts `systemd-timesyncd` whenever the
clock is not synchronised. It follows `nas-mounts.service` — on this board the
network comes up late, so anything that matters needs a retry rather than a
single attempt at boot. It does not replace the battery; it removes the
consequences of its death.

Worth remembering when something authenticates against a remote service and
fails for no visible reason: check `date` on the board before suspecting the
credentials.

Result: 43 tuya entities, 35 live, 10 devices. The plug this started from is
registered as `T34-Smart Plug+` — `switch.t34_smart_plug_switch_1` plus
voltage, current, power and total-energy sensors. Searching the registry for
"t34-smartplug" finds nothing; the name carries a space and a plus sign.
