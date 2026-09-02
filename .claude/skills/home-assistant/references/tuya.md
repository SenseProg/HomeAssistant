# Tuya: two channels, and which one a change may depend on

Every Tuya device in this house can be reached two ways, and the difference
decides whether a feature survives a cloud outage. Verified 2026-09-02.

## The two channels

**Cloud — the `tuya` integration.** It runs on `tuya_device_sharing_sdk 0.2.10`
(`tuya_sharing`), i.e. a Smart Life **app account** linked by QR login. It is
*not* the old Access ID/Secret style integration, and it does not call the
account's project on `iot.tuya.com`. Config entries are titled by account:

| Entry title | State |
|---|---|
| `roman.d.kovtun@gmail.com` | loaded, 69 entities |
| `gg-115632026641134384580` | loaded, 6 entities |

A third entry, `Yaroslav.d.kovtun@gmail.com`, was removed on 2026-09-02: it was
stuck in `setup_error` (`Authentication failed`) with 0 devices and 0 entities,
and every startup it duplicated the first account's devices and filled the log
with `Platform tuya does not generate unique IDs … already exists - ignoring`.
Do not re-add a second account that owns the same devices.

**Local — the `localtuya` custom integration.** 85 entities over LAN TCP 6668
with the device's local key. This is the execution path for irrigation, the well
pump, the EV charger and the inlet meter.

## The Tuya IoT Platform subscription is a third thing, and nothing runs on it

A "Power Management" value-added service on `iot.tuya.com` expired 2026-09-02.
Home Assistant does not call it. Its only consumers are three **manual** scripts
on the board that read the developer Cloud API with credentials in
`/home/forlinx/.tuya_cloud.json`:

- `config/scripts/tuya_history.py` — GET only, by design
- `config/scripts/tuya_energy_register.py` — the one script that writes
- `config/scripts/tuya_app_probe.py`

No systemd timer, no `shell_command`, no automation invokes them. The energy
module they query returned all-zero rows even while the subscription was valid;
`tuya_energy_register.py` documents that finding in its own docstring.

Keep the project credentials anyway: extracting a **local key** for a newly
paired device still goes through that project. That is a one-off operation and
needs no value-added subscription.

## Which devices have a local twin

Anything with a twin must be driven locally. The cloud copy stays as a manual
fallback on a dashboard, or as the last retry in an automation.

| Device | Cloud entity | Local twin |
|---|---|---|
| Inlet meter `.219` | `sensor.energy_meter_total_energy` | `sensor.energy_meter_local_total_energy_local` (DP 1), plus `sensor.merezha_spozhyto` |
| Irrigation controller `.221` | `switch.avtopoliv_kontroler_switch_N` | `switch.avtopoliv_kontroler_avtopoliv_klapan_N` |
| Well pump T34 `.26` | `switch.t34_smart_plug_switch_1` | `switch.t34_smart_plug_switch_1_2` |
| EV charger `.36` | `switch.zariadka_7_5kvt_switch` | `switch.zariadka_7_5kvt` |
| Granny's boiler | `switch.smart_plug_socket_1` | `switch.boiler_babusi_socket` |
| Irrigation pump K601 (2nd) | `switch.mini_switch_k601_2_switch_1` | `switch.mini_switch_k601_2_switch_1_2` |
| Small washing machine | `switch.mala_pralka_socket_cloud` | `switch.mala_pralna_mashina_socket` |
| Dryer | `switch.sushka_socket_cloud` | `switch.sushka_socket` |

## Cloud-only: no local channel exists

These are the only things a Tuya account outage still takes down.

| Entity | What it is | State on 2026-09-02 |
|---|---|---|
| `sensor.2i_poverkh_t_h_*` | "Дім бабусі" temperature/humidity | live, 6 references on dashboards |
| `sensor.t_h_sensor_2_*` | T&H sensor, second account | live |
| `sensor.na_dvori_t_h_*` | Outdoor T&H | `unavailable` |
| `sensor.t_h_sensor_*` | T&H sensor, first account | `unavailable` |
| `sensor.velika_pralka_*`, `switch.velika_pralka_*` | Measuring socket of the big washing machine | `unavailable`, 0 references |
| `switch.mini_switch_k601_switch_1` | First K601 relay | `unavailable`, 1 reference |
| `sensor.energy_meter_total_production` | Meter's export register | live, 0 references |

The temperature/humidity sensors are the real exposure. They are battery sensors
paired to the app, so a local channel means a Zigbee gateway or Zigbee2MQTT, not
a LocalTuya entry — a hardware decision, not a config one.

## The rule

Do not bind an automation, a `utility_meter`, or an Energy dashboard source to a
cloud Tuya entity when a LocalTuya twin exists. This has already cost real data
twice: on 2026-08-09 an expired token froze the whole grid import for ten days,
and on 2026-08-27 a cloud `Remote api run unknown failed` left the boiler cold
for a day.

Two deliberate exceptions remain, both about not breaking an accumulated total:

- `utility_meter boiler_babusi_za_tarifom` and the "Спожито всього" tile still
  read `sensor.smart_plug_total_energy`, because `sensor.boiler_babusi_energy`
  counts from a different origin (1.19 vs 1.908 kWh on 2026-09-02).
- The dryer has local power but **no** local energy entity, so its cumulative
  figure has no local source at all.

## Logging

`tuya_sharing: warning` in `logger`. Never set it to `debug`: on 2026-08-09 it
grew `home-assistant.log` to 74 MB in four days and filled `/userdata`.
`homeassistant.components.tuya: debug` was kept for QR-login diagnostics; remove
it once cloud re-authentication is finished.
