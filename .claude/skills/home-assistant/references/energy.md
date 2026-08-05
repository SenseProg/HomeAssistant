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

## Troubleshooting missing daily energy

1. Check that the source entity is available and increasing.
2. Confirm `device_class: energy`, `state_class: total_increasing`, and kWh.
3. Inspect recorder/statistics availability rather than the raw graph alone.
4. Check for a source switch in Energy preferences.
5. Explain the hourly/statistics delay in the dashboard instead of showing a
   misleading zero.
