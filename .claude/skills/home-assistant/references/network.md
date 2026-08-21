# Network inventory and naming

ASUS RT-AX55 is `192.168.50.1`. The fixed DHCP inventory is also available via
the project MCP `network_inventory` tool and `mcp-server/network_inventory.json`.

| IP | Hostname | MAC | Function |
|---|---|---|---|
| `.2` | `Tenda-AP` | `B4:0F:3B:38:3F:50` | Tenda access point |
| `.13` | — | `30:83:98:C1:6E:AC` | Terneo thermostat 1 |
| `.15` | — | `34:6F:24:B5:AD:4B` | HomeMate PC |
| `.25` | — | `00:08:9B:ED:62:EF` | CloudMate QNAP NAS |
| `.26` | `Well-Pump` | `86:0F:3B:0A:36:91` | T34 well-pump plug, LocalTuya 3.5; DHCP reservation not yet verified |
| `.27` | `Blauberg-Boys` | `98:F4:AB:EE:A5:C5` | Recuperator, boys' room |
| `.36` | `EV-Charger` | `3C:0B:59:11:9A:13` | Tuya EV charger |
| `.91` | `Irrigation-Pump` | `80:64:7C:46:E8:D1` | Irrigation pump relay |
| `.102` | `Tenda-Repeater` | `50:0F:F5:99:04:E8` | Tenda repeater |
| `.118` | — | `04:D6:F4:70:AD:B3` | Midea water heater |
| `.123` | `Blauberg-Olesia` | `98:F4:AB:EE:A8:4E` | Recuperator, Olesia's room |
| `.141` | — | `66:55:7E:21:D0:AC` | MB35x8 Home Assistant board |
| `.157` | — | `E0:98:06:AF:B7:41` | Terneo thermostat 2 |
| `.164` | `SONOFF-ZBBridge` | `84:CC:A8:96:28:A7` | Sonoff Zigbee bridge |
| `.175` | `TV-TCL` | `F0:35:75:B3:31:80` | TCL television |
| `.176` | `Garage` | `08:3A:F2:2D:32:30` | Garage controller |
| `.179` | `Deye-Inverter` | `D4:27:87:50:23:6C` | Solarman logger, TCP 8899 |
| `.201` | `Hikvision-Cam1` | `10:12:FB:F7:95:AD` | Hikvision camera |
| `.219` | `Energy-Meter` | `D8:D6:68:31:BA:49` | Three-phase energy meter |
| `.221` | `Irrigation` | `38:2C:E5:2D:5B:32` | Eight-channel irrigation controller |
| `.246` | `PRANA-Parents-Bedroom` | `14:2B:2F:E1:54:60` | PRANA recuperator |

## ASUS apply behavior

The DHCP page logs out after Apply because DHCP/web services restart. Re-login
and read the saved table before reporting success. A reserved device can ignore
ICMP while its service port remains live; for example the Deye logger may not
ping but TCP 8899 proves it is reachable.

## Presence

ASUSWRT creates device trackers but disables many by integration. When a phone
is visible under an AP but absent from “Хто вдома”, check the entity registry
state through supported HA UI/API before changing YAML. Do not infer presence
from one AP card alone; clients roam between ASUS and both Tenda devices.
