---
name: mb35x8-bench
description: Diagnose and service the MB35x8 carrier with a Forlinx RK3568J SoM, including Ubuntu access, SSH, boot/power failures, debug UART, storage, zram, vendor-kernel limits, pinout, and risky flashing decisions. Use when the board is unreachable, reboots, needs OS/hardware inspection, serial-console work, image recovery, kernel/container evaluation, or MB35x8 electrical-interface investigation.
---

# MB35x8 bench

## Production board facts

- Physical unit: MB35x8 v1.0, hand-marked board 1.
- SoM: Forlinx RK3568J/FET3568-C family.
- OS: Ubuntu 20.04.6, not Android.
- Kernel: 4.19.206, vendor build.
- Network: `192.168.50.141`, hostname `ok3568`.
- Normal access is SSH over Ethernet, not ADB or the debug UART.

```powershell
ssh.exe -i 'C:\SPB_Data\.ssh\mb35x8_ed25519' -o BatchMode=yes `
  forlinx@192.168.50.141
```

Never add `-b 192.168.50.111`; the old Hyper-V bridge was removed and binding
to it fails with `Cannot assign requested address`.

## Diagnose a disappearance

1. Ping `.141` and request `http://192.168.50.141:8123/`.
2. Check the ASUS lease/reservation before assuming the IP moved.
3. If SSH works, inspect `uptime`, `last -x reboot`, `journalctl --list-boots`,
   `dmesg`, temperatures, voltage/power evidence, and disk space.
4. Distinguish a full-board power loss from a Home Assistant restart.
5. Suspect supply, connectors, RTC battery, and physical link before modifying
   software when journals end abruptly with no OOM/panic.
6. After any reboot check the clock the services started under: `date` and
   `systemctl show home-assistant -p ActiveEnterTimestamp --value`. The RTC is
   dead, every boot starts on 2024-06-17, and a service that started before
   NTP keeps living with that start (TLS "not yet valid", `setup_error` in
   cloud integrations, localhost banned by HA) until it is restarted.
   `journalctl --list-boots` shows a wrong boot start time after the jump; do
   not trust it. In systemd units only a whole-word `$VAR` argument or `${VAR}`
   is substituted; `$i` inside a quoted `sh -c` string is left alone (verified
   2026-09-04), `%` needs `%%`. `ExecStartPre=` runs as the unit's `User=`
   unless the executable is prefixed with `+`.

Recorder unclean-shutdown messages are consequences of abrupt board loss, not
proof that SQLite caused it.

## Memory and storage

- Active swap: 1 GiB zram (`/dev/zram0`).
- Do not recreate the removed 4 GiB eMMC swapfile.
- Use `du -x` under `/userdata` so NAS media mounts are not traversed.
- Check both `/` and `/userdata`; either can block HA or token persistence.

## Container limitation

The installed kernel lacks overlayfs, veth, memory cgroups, and PID cgroups.
Docker, HA OS, and HA Supervised are not supported on this image. Do not install
or repeatedly retry Docker. A migration requires a separately validated vendor
kernel/image and a recovery plan.

## Debug UART

Read `references/hardware.md` before attaching serial hardware or flashing.
The Type-C debug path has a known U9 RX/TX routing defect on several board
revisions. P25 is the fallback and may be output-only. Settings are 115200 8N1,
no flow control.

## Flashing guardrail

Treat reflashing as destructive and production-risky. Before any attempt:

1. Identify the exact board revision and physical board number.
2. Capture existing partition/image metadata and verify off-board backups.
3. Confirm serial recovery or Maskrom access.
4. Validate the image against the MB35x8 v1.0 production board, not only v1.1
   test logs.
5. Obtain explicit user approval for the exact image and downtime.

Do not infer that a defect documented for board 4 or 5 applies to board 1.
