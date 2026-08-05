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

Do not use the old ambiguous `switch.avtopoliv_kontroler_switch_N` identifiers
for new logic. Before removing old references, confirm whether they are duplicate
cloud entities retained for compatibility.

## Two layers

Irrigation Unlimited owns sequencing and physical execution. Smart Irrigation
calculates demand from weather/evapotranspiration. Direct valve control in Smart
Irrigation remains off; link zones to the physical valve entities but let the
existing execution layer perform safe pump/valve ordering.

Dashboard manual starts for zones owned by Irrigation Unlimited must call
`irrigation_unlimited.manual_run`; never turn their physical valve and master
pump switches on directly. Irrigation Unlimited synchronises owned switches to
its logical state, so an out-of-band `switch.turn_on` is immediately corrected
back to `off`. A global Stop must cancel the Irrigation Unlimited controller
before applying the pump-first, valve-second hardware fallback.

Never let a delayed Tuya cloud state abort a known-good local run. Safety guards
must use the local valve/pump entities and Irrigation Unlimited binary sensors.

## Before changing schedules

1. Confirm no live watering run.
2. Compare `automations.yaml` and `scripts.yaml` with the board.
3. Remove expired one-off test automations before committing, but never delete a
   test report merely because its automation is no longer needed.
4. Validate configuration and use automation/script reloads rather than restart.
