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
