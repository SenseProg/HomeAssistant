# Energy behavior and sources

## Units and update timing

- Power is instantaneous kW/W.
- Energy is cumulative kWh.
- The native Energy dashboard uses long-term statistics and hourly aggregation;
  recent consumption can lag even while a device card updates live.
- A flat cumulative sensor is not proof that the load is off. Check power,
  source availability, state class, and the statistics sum.

## Main devices

- House import: `sensor.inverter_total_energy_import` is the preferred stable
  native Energy source when configured; verify actual Energy preferences through
  HA before assuming.
- Inlet meter: local Tuya entities at `.219` provide fresher per-phase data.
- EV charger: `.36`, dedicated dashboard and cumulative charging energy.
- Deye logger: `.179`, TCP 8899, `Deye-Inverter`; its load can represent only the
  backup/essential circuit and must not be equated with whole-house demand.
- Boiler helpers display power/energy but must not be recreated in YAML when they
  already exist as UI helpers.
- Irrigation pump energy uses measured/confirmed pump power when available; do
  not replace an actual measurement with the nominal 1.1 kW label.

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

Two fixes are needed together:

- make the value non-decreasing — `{{ [calc, this.state | float(0), 0] | max }}`;
- tighten `availability` so a zeroed source blocks the sensor instead of feeding
  garbage: `has_value(total) and states(total) | float(0) > 0`. `has_value` alone
  is not enough, because a source that returns a valid `0` passes it.

Repair the already-written history with the recorder's own WebSocket command —
one call fixes that point and everything after it:

```
recorder/adjust_sum_statistics
statistic_id, start_time (exact hour), adjustment, adjustment_unit_of_measurement
```

Beware the timezone when reading `period: day` results: `start` comes back in UTC,
so a Kyiv day looks shifted one day earlier and you diagnose the wrong date.

## Troubleshooting missing daily energy

1. Check that the source entity is available and increasing.
2. Confirm `device_class: energy`, `state_class: total_increasing`, and kWh.
3. Inspect recorder/statistics availability rather than the raw graph alone.
4. Check for a source switch in Energy preferences.
5. Explain the hourly/statistics delay in the dashboard instead of showing a
   misleading zero.
