# Irrigation safety and entity model

## Physical order

- Start: open the selected valve, confirm it is on, then start the pump.
- Stop: stop the pump first, wait for pressure to fall, then close the valve.
- There is **no** runtime limit on the pump. The automation
  `irrigation_pump_max_runtime_3h` keeps `max_runtime_hours: 0` on purpose:
  hose watering through the garden hydrants takes as long as it takes. The name
  is historical; do not "restore" three hours (README, this file and the
  assistant prompt all said three hours until 2026-09-02 — that text was wrong).
- Every Stop/emergency action must stop the pump and all physical valves.

## The pump may always be started, with or without a valve

Corrected 2026-08-08 by the owner, and this is not a special mode — it is the
normal state of affairs. The property has garden hydrants: water outlets that
take a hose. The pump is switched on often and casually — the physical button on
the module, the toggle in the interface, whatever is at hand — and running it
with every zone valve closed is an ordinary event, **never an emergency**.

Manual pump start therefore has **no conditions and no options at all**. Switch
it on and it simply runs. Nothing opens a valve for you, nothing stops it for
lacking one.

The configuration used to assume the opposite. Two automations were built on
that assumption and are now **deleted**, not disabled:

- `irrigation_manual_pump_opens_valve` — force-opened the zone chosen in
  `input_select.poliv_ruchna_zona` on every manual start. The owner had "Зона 5"
  selected, so every hose watering also flooded zone 5.
- `irrigation_pump_without_open_valve` — killed the pump three minutes after it
  ran without a valve.

The helper `input_select.poliv_ruchna_zona` is deleted too, together with its
dashboard row. An intermediate attempt added a "Без клапана (шланг)" option to
it; the owner rejected that as needless ceremony, and it was removed. Do not
bring back a mode selector for this.

What remains as protection: `irrigation_close_valves_when_pump_idle` (clears a
valve left open after the pump has been off for five minutes) and the
`irrigation_watchdog_master_without_valve` guard for scheduled runs.
`irrigation_pump_max_runtime_3h` exists but is set to 0 = no limit.

Do not reintroduce any dry-run interlock, any "pump on with no valve" fault, or
any condition gating manual pump start. `sensor.poliv_stan_sistemi` has no
emergency state left: pump plus an open valve reads `ПОЛИВАЄ — ЗОНА N`, pump
alone reads `ПОЛИВАЄ — ШЛАНГ`. It scans all eight valves — it used to check only
zones 1-3, so a zone 4 or 5 run displayed as an emergency.

## Authoritative entities

- Pump: `switch.mini_switch_k601_2_switch_1_2`.
- Physical LocalTuya valves:
  `switch.avtopoliv_kontroler_avtopoliv_klapan_1` through `_8`.
- Irrigation Unlimited master:
  `binary_sensor.irrigation_unlimited_c1_m`.
- Irrigation Unlimited zones include
  `binary_sensor.irrigation_unlimited_c1_z1` and `_z2`.
- User Stop script: `script.poliv_stop_all`.

Do not use the old ambiguous `switch.avtopoliv_kontroler_switch_N` identifiers;
they are obsolete, nonexistent cloud-style entity IDs. The eight
`switch.avtopoliv_kontroler_avtopoliv_klapan_N` LocalTuya entities are the
physical source of truth.

## Control path and readiness

The irrigation execution path is **local**, not cloud Tuya:

- HA's custom LocalTuya integration maintains a LAN TCP session to the DP-WBS01
  controller at `192.168.50.221:6668`.
- Valve preflight uses `localtuya.set_dp`; valve feedback comes from the eight
  LocalTuya switch entities above.
- Irrigation Unlimited sequences those local valve entities and the local pump
  relay entity. A Tuya cloud integration may exist for other devices, but it is
  not the irrigation safety or execution path.

Run `ha_irrigation_health` through MCP or
`python mcp-server/cli.py irrigation-health` before diagnosing or starting a
test. Interpret the layers separately:

1. `ping` plus ARP MAC `38:2C:E5:2D:5B:32` proves only that the controller is on
   the LAN. It does **not** prove LocalTuya control works.
2. `controller_localtuya=established` must show that the HA process owns an
   established TCP session to `.221:6668`. Do not use an independent `nc` port
   scan as the deciding signal; a Tuya device can reject a second connection
   while HA's existing session is healthy.
3. No controller handshake, connection, unavailable, or synchronisation errors
   may appear in the last ten minutes.
4. For full irrigation readiness, the pump relay at `.91:6668` must also have an
   established HA LocalTuya session and no recent errors.
5. Before physical operation, the selected valve entity and pump entity must be
   `on` or `off`, never `unknown`/`unavailable`. The definitive actuator proof
   is still a controlled command followed by the selected valve reporting `on`
   within eight seconds.

`controller_ready=true` means the controller transport is ready.
`irrigation_ready=true` additionally means the pump transport is ready. Neither
flag proves water flow, 24 V AC output, wiring, or solenoid movement; physical
commissioning remains required for that.

## Two layers

Irrigation Unlimited owns sequencing and physical execution. Smart Irrigation
calculates demand from weather/evapotranspiration. Direct valve control in Smart
Irrigation remains off; link zones to the physical valve entities but let the
existing execution layer perform safe pump/valve ordering.

Dashboard manual starts for zones owned by Irrigation Unlimited must perform a
physical-valve preflight and then call `irrigation_unlimited.manual_run`; never
turn the master pump on directly. The preflight must set the valve DP together
with its device timer, wait for the physical switch entity to report `on`, and
stop with a persistent notification if confirmation does not arrive. Only a
confirmed valve may proceed to Irrigation Unlimited, which then owns the run.
Dashboard starts must pass `queue: false` so a click replaces any older manual
request and starts immediately; `queue: true` is reserved for the multi-zone
scheduler and can accumulate future 25-minute runs. A global Stop must cancel
the Irrigation Unlimited controller before applying the pump-first, valve-second
hardware fallback.

Never let a delayed Tuya cloud state abort a known-good local run. Safety guards
must use the local valve/pump entities and Irrigation Unlimited binary sensors.

## The controller closes its own valves; always set its timer first

Measured on 2026-08-10 and no longer a hypothesis. `irrigation_unlimited.manual_run`
switches only the valve DP, so the controller falls back to whatever countdown it
already holds — about ten minutes — and closes the valve itself while Irrigation
Unlimited keeps the master pump running for the full requested duration.

The zone 5 test that settled it:

- Phase A, no timer written: valve open 10:26:18, closed 10:36:21 — 10 min 03 s —
  while `binary_sensor.irrigation_unlimited_c1_z4`, the master and the pump stayed
  `on` for another 2.5 minutes.
- Phase B, `localtuya.set_dp` DP 17 = 900 written **before** `manual_run`, with the
  valve still closed: the valve stayed open the whole 13 minutes and Irrigation
  Unlimited ended the run correctly — pump at 10:54:09, valve at 10:54:13.

Consequences that matter:

1. Any path that starts a zone through Irrigation Unlimited must first write that
   zone's timer DP with an integer of the intended duration plus about a minute of
   margin, while the valve is still closed. The hardware countdown is then a
   backstop, and Home Assistant still owns the stop.
2. Writing a timer DP into an already-open valve is untested. Do not do it.
3. Irrigation Unlimited will not notice a valve closing mid-run: `check_back`
   watches for roughly ninety seconds after the command (three tries thirty
   seconds apart) and then stops. A valve that fails later leaves the pump running
   against closed heads until the cycle ends. On the night of 2026-08-10 that was
   about fifty minutes.

`irrigation_switch_source_log` records every pump and valve transition with its
Home Assistant context and flags `POLIV-АНОМАЛІЯ` when a valve closes while the
Irrigation Unlimited master is still watering. Context alone cannot separate
Irrigation Unlimited from the controller — Irrigation Unlimited calls services
with a fresh context and no `parent_id`, so its commands look context-free too.
Only a `user_id` reliably proves a human pressed something in the interface.

## DP-WBS01 controller diagnostics

The eight-zone controller at `192.168.50.221` matches the DP-WBS01 family:

- DP 1-8: zone valve outputs.
- DP 13-20: corresponding hardware run timers in seconds. Zone N uses DP 12+N:
  zone 1 is DP 13, zone 3 is DP 15, zone 5 is DP 17.
- DP 25-32: elapsed/used time.
- DP 40: controller-wide automatic sequence state.
- DP 42: the controller's own Smart Weather switch. Keep it off because Smart
  Irrigation is the single weather authority in Home Assistant.

For a manual preflight, send a multi-DP LocalTuya command such as valve 1 plus
timer 13, then require the physical valve entity to report `on` within eight
seconds. If the controller acknowledges the command but resets its timer to zero
without ever reporting the valve `on`, treat this as a controller-side watering
anomaly. Do not start the pump. Check the controller's 24 V AC supply, common
wire, zone output wiring, and the magnetic-valve solenoid before changing Home
Assistant logic.

## Before changing schedules

1. Confirm no live watering run.
2. Compare `automations.yaml` and `scripts.yaml` with the board.
3. Remove expired one-off test automations before committing, but never delete a
   test report merely because its automation is no longer needed.
4. Validate configuration and use automation/script reloads rather than restart.
