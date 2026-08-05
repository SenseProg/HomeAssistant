# Irrigation safety and entity model

## Physical order

- Start: open the selected valve, confirm it is on, then start the pump.
- Stop: stop the pump first, wait for pressure to fall, then close the valve.
- Maximum continuous pump runtime: three hours.
- Every Stop/emergency action must stop the pump and all physical valves.
- If the pump is on with no confirmed valve, execute emergency stop immediately.

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
