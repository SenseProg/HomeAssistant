# Well-water monitoring and calibration

## Distinguish the two pumps

The well pump is the `T34-Smart Plug+` at `192.168.50.26`; it supplies the
property's main water system. It is not the irrigation pump relay at `.91`.
Do not apply irrigation valve sequencing or the three-hour irrigation safety
model to this device unless the owner explicitly asks for a shared rule.

The T34 is configured in LocalTuya 2026.07.0 with protocol 3.5 and a one-second
scan interval. The local key remains only in Home Assistant storage. Never read,
copy, log, commit, or return it. The observed MAC is `86:0F:3B:0A:36:91`; confirm
that the ASUS DHCP reservation for `.26` exists before treating the address as
permanent.

Run `ha_well_pump_health` through MCP or
`python mcp-server/cli.py well-pump-health` before diagnosing the local path.
The check is transport-only and never actuates the pump.

## Authoritative local entities

| Purpose | Entity |
|---|---|
| Relay | `switch.t34_smart_plug_switch_1_2` |
| Power | `sensor.t34_smart_plug_power_2` |
| Current | `sensor.t34_smart_plug_current_2` |
| Voltage | `sensor.t34_smart_plug_voltage_2` |
| Device electricity DP | `sensor.t34_smart_plug_electricity` |
| Own integrated energy | `sensor.t34_smart_plug_nasos_sverdlovini_spozhito` |
| Running state | `input_boolean.nasos_sverdlovini_pratsiuie` |

The unsuffixed switch, power, current, voltage, and total-energy entities are
the Tuya cloud copies. Keep them as fallback/control unless the owner requests
their removal. New dashboards, running-state logic, and integrations must use
the `_2` LocalTuya power and switch entities.

Do not replace the own integrated-energy helper with the LocalTuya
`sensor.t34_smart_plug_electricity` merely because both are in kWh. At cutover
the local DP did not match the cloud cumulative total. The own helper integrates
local power with the left Riemann sum and is the calibration source; its value
of `0.1113 kWh` was preserved when its source changed to local power on
2026-08-21.

Automation `well_pump_running_state` triggers from local power and considers the
pump active above 20 W. The water-estimation automation consumes the own
integrated-energy helper rather than either native Tuya total.

## One-second scanning versus recorded history

The LocalTuya device scan interval is one second. That does not imply one
Recorder row per second: Home Assistant normally stores state changes, so a
steady 0 W or unchanged running value can keep the same `last_updated` time.
Validate cadence during a real run from raw local state changes, not from the
number of rows while idle.

The dashboard's `points_per_hour` is display aggregation, not device polling.
The previous `12` points/hour produced five-minute buckets even though start and
stop events had sub-second timestamps. Keep two purposes distinct:

- the one-hour history graph shows raw local power changes without averaging;
- the 24-hour graph may aggregate for readability and must label its interval.

Pump starts are rendered by `well-pump-runs-card`, not the built-in grey binary
history graph. Active intervals use cyan `#00bcd4` on a dark inactive track and
the card reports launch count plus total runtime for 24 hours and 7 days. Keep
the inactive track visually subordinate; grey must never represent an active
pump interval.

Hourly estimated water is rendered by `well-hourly-water-card` from deltas of
the own integrated-energy history, not by `mini-graph-card` over the cumulative
water helper. It uses 24 stable one-hour buckets, applies the calibration offset
at `2026-08-20T23:23:18+03:00`, and displays litres per hour. The complete
calculated-water section is intentionally the first section of the well
dashboard because daily, weekly, and 30-day water use are primary information.

Local history begins around 08:17 Europe/Kyiv on 2026-08-21. Older cloud history
remains in the unsuffixed power entity and must not be described as deleted.

## Water calculation state

There is no electronic flow sensor. Estimated water is calibrated from energy
between mechanical readings:

`water m³ = integrated pump energy kWh × calibrated m³/kWh`

The mechanical baseline is `814.79 m³` at 2026-08-20 23:23 Europe/Kyiv, taken
after the first recorded pump start. The calculation includes a fixed
`0.01748706 kWh` offset for pump energy after that baseline but before the own
integrator existed. A later mechanical reading establishes the first usable
coefficient; each subsequent reading refines it.

The `sverdlovina-dashboard` dashboard, the reading log, and several helpers are
storage-managed. Inspect and change them only through supported Home Assistant
UI/API flows in an authorized session. Never inspect `.storage` directly to
recover their configuration.

The current calibrated coefficient is exposed in both directions on the water
dashboard: litres per kWh and kWh per cubic metre. `well-daily-water-card`
builds the last-30-days daily bars from the history of the own integrated-energy
helper, applies the fixed offset on 2026-08-20, and recalculates all displayed
days whenever the coefficient changes. `well-water-overview-card` is the compact
variant for the YAML Overview dashboard; it shows calculated litres today and
in the current calendar month and links back to the well dashboard.

Both YAML dashboards use the physical irrigation relay
`switch.mini_switch_k601_2_switch_1_2`, not the well-pump relay. Keep the
irrigation pump control prominent in the Overview hero and at the top of the
`poliv` view. A temporary resource-level overlay provides the same controls
when those YAML files cannot yet be deployed; it must suppress itself once the
native cards are present so the UI never shows duplicates.

## Safe verification

1. Confirm MCP transport readiness: expected IP/MAC, established HA TCP session
   to port 6668, and no recent matching LocalTuya errors.
2. Confirm the dashboard, running automation, and integrated-energy helper point
   to local power; verify the accumulator did not reset.
3. Observe the next natural pump run. Do not switch the pump solely for a test
   unless the owner explicitly authorizes actuation.
4. Compare local and cloud timestamps during that run. Local changes should be
   the monitoring source; cloud data remains only a control.
5. Treat a constant value with sparse Recorder rows as normal. Treat
   `unavailable`, a missing TCP session, or repeated LocalTuya errors as a
   transport problem.
