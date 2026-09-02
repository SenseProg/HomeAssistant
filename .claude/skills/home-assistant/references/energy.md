# Energy behavior and sources

## Units and update timing

- Power is instantaneous kW/W.
- Energy is cumulative kWh.
- The native Energy dashboard uses long-term statistics and hourly aggregation;
  recent consumption can lag even while a device card updates live.
- A flat cumulative sensor is not proof that the load is off. Check power,
  source availability, state class, and the statistics sum.

## Main devices

- Grid source of the native Energy dashboard: `sensor.merezha_spozhyto`, since
  2026-09-02. It is the local template sensor built on LocalTuya DP 1 of the
  inlet meter, with the anchor helpers bridging the first minutes after a
  restart. It replaced the cloud `sensor.energy_meter_total_energy`, which had
  been the last thing on the Energy dashboard that a Tuya token expiry could
  freeze. Its statistics begin on 2026-08-23, so the panel shows no grid history
  before that date; the cloud statistic still accrues untouched, and putting the
  old id back in Energy preferences restores the full series.
- `sensor.inverter_total_energy_import` is **not** the grid source: the Deye sits
  downstream of the meter and never sees loads outside its branch. Keep it for
  PV/battery/inverter detail only.
- Inlet meter: local Tuya entities at `.219` provide fresher per-phase data.
- EV charger: `.36`, dedicated dashboard and cumulative charging energy.
- Deye logger: `.179`, TCP 8899, `Deye-Inverter`; its load can represent only the
  backup/essential circuit and must not be equated with whole-house demand.
- Boiler helpers display power/energy but must not be recreated in YAML when they
  already exist as UI helpers.
- Granny's boiler is switched **locally**: `switch.boiler_babusi_socket`
  (LocalTuya), with the cloud `switch.smart_plug_socket_1` kept only as the sixth
  and last retry in both night-tariff automations. Its instantaneous readings on
  the Devices tab are local too. The one deliberate exception is the tile
  "Спожито всього" and the utility meter `boiler_babusi_za_tarifom`, which still
  read the cloud `sensor.smart_plug_total_energy`: the local
  `sensor.boiler_babusi_energy` counts from a different origin (1.19 vs 1.908 kWh
  on 2026-09-02), so swapping it in would break the accumulated total. Move that
  one only together with a statistics migration.
- Irrigation pump energy uses measured/confirmed pump power when available; do
  not replace an actual measurement with the nominal 1.1 kW label.
- Well-pump power is the LocalTuya entity `sensor.t34_smart_plug_power_2` at
  `.26`. Water calibration uses
  `sensor.t34_smart_plug_nasos_sverdlovini_spozhito`, whose source is that local
  power entity. Keep the unsuffixed Tuya entities only as cloud controls.

## Whole-site power flow and the Deye branch

The three-phase meter at `.219` is upstream of Deye and measures the entire
property. `sensor.inverter_grid_power` measures only the branch entering Deye.
The instantaneous topology is therefore:

```
grid inlet = Deye grid branch + consumption outside Deye
Deye = protected house load + battery + PV (when installed)
```

The dashboard uses these reproducible template sensors:

- `sensor.merezha_potuzhnist_usogo_vvodu` —
  `sensor.zagalne_navantazhennia * 1000`, W;
- `sensor.spozhivannia_poza_invertorom` — whole inlet minus
  `sensor.inverter_grid_power`, clamped at zero to suppress update-order noise.

For `custom:sunsynk-power-flow-card`, map `grid_ct_power_172` to the whole inlet,
`grid_power_169` to the Deye branch, and `nonessential_power` to the difference.
Use `cardstyle: full`: the installed card does not render the nonessential branch
in its lite or compact layouts. The full layout has been visually verified with
the live example `1550 W total = 803 W Deye + 747 W outside Deye`.

Run `ha_energy_flow_health` or `python mcp-server/cli.py energy-flow-health` to
check the split. Do not silently substitute Deye import for the whole-site grid
value on the diagram or in daily purchase totals.

## Well-pump cadence and energy

The T34 well-pump plug uses LocalTuya 3.5 with a one-second scan. Recorder still
stores changed states rather than one idle row per second; dashboard aggregation
also does not prove or disprove device cadence. Read
`references/well-water.md` before changing its integrator, graph source, or
mechanical-water calibration.

## "Unit cannot be converted" — fix the metadata, never delete the history

Symptom in the log, repeated for several sensors:

```
The unit of sensor.merezha_za_tarifom_nich (kWh) cannot be converted to the unit
of previously compiled statistics (None). Generation of long term statistics
will be suppressed
```

It means the statistics were first compiled while the sensor had no unit, the
sensor later gained `kWh`, and the recorder refuses to mix the two. Long-term
statistics stop growing — daily and monthly charts silently freeze. Eight
tariff meters were in this state on 2026-08-09.

The values were already in kWh; only the label was missing, so **nothing needed
converting and nothing needed deleting** — just relabelling:

```
recorder/update_statistics_metadata
  statistic_id: sensor.…
  unit_class: energy          # ← without this the call succeeds and does nothing
  unit_of_measurement: kWh
```

Two traps cost real time here:

- **`unit_class` is effectively required.** Omit it and the command still returns
  `success: true`, logs a deprecation warning, and silently leaves the metadata
  untouched. `energy` is the class for kWh.
- **`get_statistics_metadata` has no `unit_of_measurement` field.** It returns
  `statistics_unit_of_measurement`, `display_unit_of_measurement` and
  `unit_class`. Reading the wrong key shows `None` forever and makes a working
  fix look broken.

Verify with 5-minute statistics, not hourly: hourly compilation runs once per
hour, so a fix applied at :20 shows nothing until the next full hour, whereas
`period: 5minute` proves within minutes that the sum is accumulating again — and
that it continues from the old totals instead of restarting at zero.

`recorder/change_statistics_unit` is the other command in this area, but it
*converts* every stored value; use it only when the old numbers really are in a
different unit.

## The EV charger switch does not stop a charging session

`switch.zariadka_7_5kvt` looks like the power switch and accepts commands — the
entity flips to `off` — but the station keeps charging. Confirmed on 2026-08-09:
the switch sat at `off` from 12:06:51 while `device_kw` still reported 6.3 kW at
12:09:14. LocalTuya bound it to a datapoint the station ignores mid-session.

The real control is **`select.zariadka_7_5kvt_charge_state`** with options
`Open charging` / `Close charging` / `Wait for operation`. Sending
`Close charging` stopped the session in two seconds: `device_state` → `finish`,
power 6.3 → 0.0 kW, current → 0.0 A.

Consequences for anything that reads charger state:

- never derive "station is off" from `switch.zariadka_7_5kvt`; use
  `device_state` plus `device_kw`, and treat `finish` as a normal end-of-session;
- `switch.zariadka_7_5kvt_switch` is a second switch that has been `unavailable`
  since 11:19 the same day — it may be the actual power datapoint and is worth
  re-pairing in LocalTuya;
- `device_state` spells charging as `charing` (sic) — match both spellings.

## Difference sensors with `state_class: total` corrupt their own statistics

`sensor.vitrati_inshe_bez_lichilnika` is "everything bought from the grid minus
the five metered devices". A difference like that is **not monotonic**: at night
the irrigation pump accrues hryvnia faster than the total bill grows, so the
difference dips by a few kopecks. Every dip is read by the recorder as a meter
reset, and the long-term `sum` is rebased.

On 2026-08-08 at 14:00 this became a real data failure. During a restart the
total-cost source briefly returned zero, the difference collapsed from 491 UAH
to near zero, and `sum` detached from `state` by exactly 491.66 UAH — permanently.
The per-device cost chart then showed a **−430 UAH bar on 8 August**. Note that
`state` stayed correct the whole time; only the statistics were wrong, so
comparing `state` against `sum` is what actually finds this.

The first attempt at a fix was `{{ [calc, this.state | float(0), 0] | max }}`
plus a stricter `availability`. Both were necessary and neither was sufficient,
because **a plain state-based template sensor is recomputed from scratch at every
start**: `this.state` is unknown at that moment, so the accumulated hold is lost
and the value drops to raw `calc`. That is exactly what produced a −55.89 UAH bar
on 10 August — the hour was **09:00, not the 16:55 reboot**, and the real drop
was −107.19 (the sensor had been frozen at 568.79 since 9 August 18:00, so the
hold was that large). `availability` made it worse: while unavailable, the next
render read `this.state` as `'unavailable'` → `0`, reopening the hole it closed.

The working shape, in place since 2026-08-11 (`unique_id: cost_device_other`):

- **trigger-based** template sensor — only these restore their state across a
  restart, which is what lets `max()` hold through a reboot;
- **`condition:` instead of `availability:`** — a failed condition simply skips
  the update, so the sensor keeps its last good value rather than passing through
  `unavailable`. Trade-off: dead sources freeze the number instead of showing
  `unavailable`, which for a monetary total is the lesser evil;
- triggers on all six sources, plus `time_pattern: /5` and `homeassistant: start`.

Note that `template.reload` does **not** restore state — the entity is rebuilt and
sits at `unknown` until the first trigger fires (up to five minutes). A real HA
restart does restore it. Do not mistake the reload gap for a broken fix.

Repair the already-written history with the recorder's own WebSocket command —
one call fixes that point and everything after it:

```
recorder/adjust_sum_statistics
statistic_id, start_time (exact hour), adjustment, adjustment_unit_of_measurement
```

It is reversible: the opposite adjustment at the same hour undoes it. That
matters, because the recorder database must never be copied for a backup — and
`/userdata` has no room for one anyway.

Beware the timezone when reading `period: day` results: `start` comes back in UTC,
so a Kyiv day looks shifted one day earlier and you diagnose the wrong date.
Equally, do not assume the drop happened at the reboot: read the **hourly** series
and find the hour where `change` goes negative. On 10 August the board rebooted at
16:55 but the damage was done at 09:00 by a service restart.

## «Інше» is structurally understated, not just occasionally broken

The 10 August numbers expose a deeper fault than the lost hold. Per-device
`change` that day totalled ≈125.67 UAH against ≈112.50 UAH of total grid cost —
**the metered devices out-ran the total**, so the raw difference is genuinely
negative and `max()` was merely hiding it.

The cause is topology. Every cost sensor derives the total from
`sensor.inverter_total_energy_import`, i.e. from the Deye, while the electricity
meter sits **upstream of the inverter** and the per-device meters see loads that
never pass through it. Measured confirmation: on 7 August the meter recorded
36.45 kWh against the inverter's 31.70; on 8 August, 33.37 against 24.50.

So the meter — not the inverter — is the only source that sees everything bought
from the grid, and it should become the single grid source, with the Deye kept for
PV/battery/inverter-branch detail only.

Done on 2026-09-02, and with the *local* meter sensor rather than the cloud one.
The 2026-08-11 blocker (`sensor.energy_meter_total_energy` had no statistics
since 9 August because of `tuya_sharing: network error:(1010) token is expired`)
no longer applies to the Energy dashboard: `sensor.merezha_spozhyto` reads
LocalTuya DP 1 over the LAN, so the same token expiry would now cost nothing
here. Re-authentication is still worth doing, but it is no longer a
prerequisite for anything on this panel.

## Troubleshooting missing daily energy

1. Check that the source entity is available and increasing.
2. Confirm `device_class: energy`, `state_class: total_increasing`, and kWh.
3. Inspect recorder/statistics availability rather than the raw graph alone.
4. Check for a source switch in Energy preferences.
5. Explain the hourly/statistics delay in the dashboard instead of showing a
   misleading zero.
