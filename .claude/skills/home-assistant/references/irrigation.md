# Irrigation safety and entity model

## Physical order

- Start: open the selected valve, confirm it is on, then start the pump.
- Stop: stop the pump first, wait for pressure to fall, then close the valve.
- Maximum continuous pump runtime: three hours. This is the only hard limit that
  applies in every mode.
- Every Stop/emergency action must stop the pump and all physical valves.

## The pump may legitimately run with no valve open

Corrected 2026-08-08 by the owner. The property has garden hydrants — water
outlets that take a hose. Running the pump with every zone valve closed is a
normal irrigation mode, not dry running, so **a pump without a valve is not by
itself an emergency**.

The configuration used to assume the opposite, and that assumption produced two
wrong behaviours: every manual pump start force-opened the valve selected in
`input_select.poliv_ruchna_zona`, and the watchdog killed the pump three minutes
later. A hose user therefore watered an unintended zone and then lost pressure.

`input_select.poliv_ruchna_zona` now carries a sixth option, `Без клапана
(шланг)`, alongside `Зона 1`…`Зона 5`. When it is selected:

- `irrigation_manual_pump_opens_valve` opens nothing;
- `irrigation_pump_without_open_valve` does not intervene at all;
- `sensor.poliv_stan_sistemi` reports `ПОЛИВАЄ — ШЛАНГ` instead of
  `АВАРІЯ — НАСОС БЕЗ КЛАПАНА`;
- the three-hour maximum runtime still applies.

In every other mode the previous behaviour is unchanged: a pump running with no
valve is still treated as a fault, because the user asked for a zone and the
zone did not open.

Do not reintroduce logic that treats "pump on, no valve" as an unconditional
emergency, and do not add a dry-run interlock on that basis. Ask which mode is
selected before diagnosing.

Note that `sensor.poliv_stan_sistemi` previously reported only zones 1-3, so a
zone 4 or zone 5 run displayed as an emergency; it now scans all eight valves.

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

## DP-WBS01 controller diagnostics

The eight-zone controller at `192.168.50.221` matches the DP-WBS01 family:

- DP 1-8: zone valve outputs.
- DP 13-20: corresponding hardware run timers in seconds.
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
