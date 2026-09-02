# Power outages: what the house does, and what the board does

Eleven automations and one script were added between 2026-08-27 and 2026-09-01
to survive grid outages on the Deye inverter's battery. This is their map, and
the facts about the board itself that shape them. Verified against the board
on 2026-09-02.

## The signal chain, and its single point of failure

```
Deye logger .179 (Solarman, TCP 8899)
  -> binary_sensor.inverter_grid + sensor.inverter_grid_frequency
     -> binary_sensor.svitlo_vidsutnie   (template, 30 s delay both ways)
        -> every outage automation below
  -> sensor.inverter_load_power -> sensor.spozhyvannia_zaraz_kvt (kW)
  -> sensor.inverter_battery (%)
```

Everything hangs on the logger. When it is unreachable (2026-09-02: no ping,
port closed, 202 inverter entities `unavailable`), `svitlo_vidsutnie` reads
`off` — "grid present" — purely because it has no data, `spozhyvannia_zaraz_kvt`
reads 0, and none of the outage automations can fire. `binary_sensor.invertor_zviazok`
(template, `has_value('sensor.inverter_battery')`) exists so that the Overview
hero, the badges and `cli.py health` say this out loud instead of pretending the
grid is fine.

The inverter watchdog (`inverter_bez_zviazku`, 10 min of `unavailable`) pushes a
warning that names exactly this consequence; `inverter_zviazok_vidnovleno` pairs
it. On 2026-09-02 the link flapped 13 times in a day — 39 pushes on three phones.
If that repeats, give the "restored" message a `for:` of a few minutes and rate
limit the pair; do not lower the 10-minute threshold.

## The automations

| id | What it does | Depends on |
|---|---|---|
| `svitlo_znyklo` | push to all phones: grid gone, battery %, load kW, which big loads are on, which are unreachable | `svitlo_vidsutnie` off→on |
| `svitlo_zyavylos` | paired "grid back" push | on→off |
| `bez_svitla_velyke_spozhyvannia` | load above `input_number.bez_svitla_porih_kvt` for `bez_svitla_zatrymka_hv` minutes while on battery | `spozhyvannia_zaraz_kvt` |
| `batareia_poperedzhennia` / `batareia_krytychno` | battery below `batareia_porih_uvaha` / `batareia_porih_krytychno`, second one is a critical push | `inverter_battery` |
| `bez_svitla_vymknuty_vazhke` | switches off boiler, floor heating, dryer, PRANA heater when the grid drops, and again when someone turns one back on; gated by `input_boolean.bez_svitla_vymykaty` | LocalTuya / Terneo / PRANA reachability |
| `svitlo_zyavylos_nahadaty_boiler` | reminder to re-enable the boiler after the grid returns | — |
| `bez_svitla_pralka_pratsiuie` | warning only: washing machine mid-cycle on battery is never interrupted | SmartThings washer sensors |
| `inverter_bez_zviazku` / `inverter_zviazok_vidnovleno` | logger watchdog, see above | — |
| `storozh_hotovnist_do_vidkliuchennia` | every 6 h and after start: are all of the above enabled, are the loads it must shed reachable | the list of ids inside it |
| script `spovistyty_vsikh` | one call, three phones (`sm_s918b`, `sm_s21`, `m2006c3mng`), `critical: true` pushes through Android battery saver | — |

The readiness guard lists automation ids by hand. Renaming an alias changes the
entity id and silently breaks that check; a `label` on the automations with
`label_entities()` would be more robust. Until then, keep the aliases.

## The «Блекаут» page

`Пристрої → Блекаут` (`/pristroi-dashboard/blackout`, added 2026-09-02)
gathers everything above in one place, duplicating the toggles that also live
on the Deye, Boiler and Washer tabs on purpose: hero (grid present / gone
since / inverter silent, battery %, estimated autonomy, load), the load-shed
list with its master switch, the four thresholds, the notifying automations,
the acting ones, the Yasno schedule, and a 72-hour history of the grid sensor,
the inverter link and the battery.

**Yasno** was configured on 2026-09-02 through the config-flow API (region
Київ → ПРАТ «ДТЕК Київські електромережі» → group 3.1). Entities:
`sensor.yasno_kiiv_3_1_electricity` (normal / outage / possible),
`_next_planned_outage`, `_next_probable_outage`, `_next_connectivity`,
`_status_today`, `_status_tomorrow`, `_schedule_updated_on`, and the calendars
`calendar.yasno_kiiv_3_1_planned_outages` / `_probable_outages`. Two derived
template entities: `sensor.do_vidkliuchennia_hodyn` (hours to the next outage,
planned before probable, attribute `typ`) and
`binary_sensor.vidkliuchennia_skoro` (a **planned** outage within 3 h) — the
latter is the battery-reserve switch in `docs/solar-boilers-spec.md` and adds
a line to the Overview hero. The owner also wants a second entry "by address";
it needs the street and house number, which the flow searches interactively.

`sensor.avtonomiia_batarei` (hours) = usable SOC above the critical threshold
× capacity ÷ current load. Capacity is `number.inverter_battery_capacity`
(200 Ah) × 51.2 V ≈ 10.2 kWh — taken from the inverter's own setting rather
than a second helper. It is `unavailable` whenever the logger is, on purpose.

## Thresholds live in helpers — and must not carry `initial:`

`bez_svitla_porih_kvt`, `bez_svitla_zatrymka_hv`, `batareia_porih_uvaha`,
`batareia_porih_krytychno`, `bez_svitla_vymykaty` are meant to be tuned from the
dashboard. Until 2026-09-02 each carried `initial:`, which Home Assistant applies
on **every** start — so every power cut reset them to the YAML defaults. They
now restore their last value; the defaults apply only when a helper is first
created.

## What happens to the board when the power goes

The MB35x8 is not on protected power: with the grid it goes down too. On
2026-09-02 the journal of the previous boot ends mid-traceback at 11:33 and the
next boot starts at 15:05 — three and a half hours without a controller, without
watchdogs, without pushes. Consequences the automations cannot cover:

- `/userdata` is ext4 **without a journal**; every hard power-off adds
  superblock errors (see `platform.md`). The `userdata_fs_broken` automation
  pushes daily at 09:30 until someone runs `fsck-userdata.sh`.
- After the board comes back: `irrigation_fail_safe_on_ha_start` switches the
  irrigation off, LocalTuya devices stay `unavailable` for ~3 minutes,
  Irrigation Unlimited logs "Switch does not match current state", and Wi-Fi
  plugs that did not rejoin the network (T34 well pump `.26`, small washer
  `.82` on 2026-09-02) stay `unavailable` until someone power-cycles them.
- The RTC battery is dead: the clock is wrong until NTP catches up, and `last`
  shows boots in 1970.

Durable fixes, in order: protected power or a small UPS for the board;
`tune2fs -O has_journal` on the unmounted `/userdata`; a "board rebooted" push
with the start time and what fail-safe switched off; DHCP reservations for every
Tuya plug so that a reconnect keeps its address.

## Do not

- Do not derive "grid present" from the meter at `.219`: it is powered by the
  same grid and simply goes `unavailable`, which also happens when its Wi-Fi
  drops.
- Do not let the assistant or a dashboard treat `svitlo_vidsutnie = off` as
  proof of grid power while `invertor_zviazok` is `off`.
- Do not add per-phone `notify.mobile_app_*` calls in new automations; call
  `script.spovistyty_vsikh` so the phone list stays in one place and the
  journal can fold the copies (see `notifications.md`).
