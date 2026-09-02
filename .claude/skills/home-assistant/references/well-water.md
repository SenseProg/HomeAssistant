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
| LocalTuya power (currently diagnostic only) | `sensor.t34_smart_plug_power_2` |
| Operational power fallback | `sensor.t34_smart_plug_power` |
| Current | `sensor.t34_smart_plug_current_2` |
| Voltage | `sensor.t34_smart_plug_voltage_2` |
| Device electricity DP | `sensor.t34_smart_plug_electricity` |
| Own integrated energy | `sensor.t34_smart_plug_nasos_sverdlovini_spozhito` |
| Running state | `input_boolean.nasos_sverdlovini_pratsiuie` |

The unsuffixed switch, power, current, voltage, and total-energy entities are
the Tuya cloud copies. Keep them as fallback/control unless the owner requests
their removal. The `_2` LocalTuya relay remains the preferred control entity.

**History, resolved 2026-08-22.** Until that evening LocalTuya `power_2` showed
only `0 W` and this file told everyone to use the cloud `power` sensor. The
cause was a missing `scan_interval` in the LocalTuya device entry, not the
hardware: with a 1-second scan the plug reports 94 % of a run instead of
0–28 %, and local and cloud energy agree (0.0553 vs 0.0555 kWh per day). Do not
"repair" LocalTuya for this again, and do not move the running-state logic or
the integrator back to the cloud entity.

Do not replace the own integrated-energy helper with the LocalTuya
`sensor.t34_smart_plug_electricity` merely because both are in kWh: DP 20 is a
per-report increment, not a cumulative total — the trigger sensor
`nasos_sverdlovini_enerhiia_prystroiu` in `configuration.yaml` sums it for
reference. The own helper stays the calibration source.

Automation `well_pump_running_state` considers the pump active above 20 W. The
water-estimation automation consumes the own integrated-energy helper rather
than either native Tuya total. If **every** T34 entity is `unavailable`, the
plug is off the LAN (ARP `FAILED`, as on 2026-09-02 after a power cut) — check
power at the socket before touching Home Assistant; `cli.py health` reports
`well_pump_ping`.

## One-second scanning versus recorded history

The LocalTuya device scan interval is one second. That does not imply one
Recorder row per second: Home Assistant stores state changes, so a steady 0 W
or unchanged running value keeps the same `last_updated` time. Validate cadence
during a real run from raw local state changes.

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

## A drop in the integrator is not a meter reset

The three water cards — `well-daily-water-card.js`, `well-hourly-water-card.js`
and `well-water-overview-card.js` — rebuild consumption by walking raw history
and summing deltas. Until 2026-08-30 all three shared this line:

```js
const delta = value >= prev.value ? value - prev.value : value;   // WRONG here
```

Any drop was treated as a counter reset, so the **entire accumulated integral**
was added to the current bucket. That rule is right for a device total that
really restarts at zero, and wrong for
`sensor.t34_smart_plug_nasos_sverdlovini_spozhito`, which is a Riemann
integrator: it never resets, but on every HA start it restores from Recorder and
comes back slightly **lower** than it actually was, because `commit_interval: 30`
did not persist the last increments.

The restart at 20:33:23 on 2026-08-30 dropped it 5.6321 → 5.5940 — 0.038 kWh —
and the daily card added 5.594 kWh whole. With the day's real 0.771 kWh that is
6.365 kWh × 802 L = **5 105 L shown instead of 618 L**; the hourly card showed
4.2 m³ in one hour the same way. So every HA restart minted a fake bar the size
of the entire integral.

The fix, applied to all three:

```js
const delta = value >= prev.value ? value - prev.value
                                  : (value <= prev.value * 0.1 ? value : 0);
```

Only a fall to near zero counts as a reset. Verified by replaying the card's own
algorithm over 9 644 real history points: 30.08 goes 5 150.8 → 664.5 L, days
23–29.08 are untouched, and the new 30-day total 4 264.6 L matches the
independent `input_number.sverdlovina_rozrakhunkova_voda` = 4.264 m³ to the litre.

Two things to remember when touching these cards:

- **`state` versus `change`.** The cards read raw history, not statistics, so
  they do not get the Recorder's own reset handling for free. Any new card that
  sums deltas needs this same guard.
- **The browser caches them, and a hard refresh is not reliable enough.** After
  editing a card the file on disk was correct and the server served it, yet the
  dashboard still drew the old bars — the browser kept the module cached under
  the unchanged `/local/…js?v=1` URL. Bump the version instead. It does not
  require touching `.storage` by hand: the Lovelace WebSocket API owns those
  records, exactly as the recorder API owns statistics.

  ```
  lovelace/resources            → list, gives each resource id and url
  lovelace/resources/update     → resource_id, res_type ("module"), url
  ```

  Rewrite the url from `?v=N` to `?v=N+1`; the changed URL is a cache miss, so
  every device reloads the module on its next page load. Done on 2026-08-30 for
  the three water cards (v1 → v2).

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
