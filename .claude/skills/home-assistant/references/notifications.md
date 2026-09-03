# Notifications: where they go, and where they are kept

Home Assistant keeps no notification history of its own. `notify.mobile_app_*`
hands the text to the phone and forgets it; `persistent_notification` lives in
RAM only and the domain is excluded from the recorder. Since 2026-08-23 the
board keeps its own journal so that an alert fired at 03:00 and dismissed by a
restart still exists in the morning. This file is the map; the pieces were
undocumented until 2026-09-02, and the journal had no card on any dashboard.

## Pipeline

```
any notify.* call, any persistent_notification.create
  -> automation notify_log_capture   (event: call_service, mode queued)
     sanitises title/message: strips ' " ` $ , truncates 120/400
  -> shell_command.notify_log
  -> config/scripts/notify_log.py log ...   (in Git: board-config/scripts/)
  -> /userdata/hass/config/notifications.db   (SQLite, WAL, never purged by age)

command_line sensor "Spovishchennia zhurnal" (sensor.spovishchennia_zhurnal)
  -> notify_log.py export --limit 40, every 5 min
  -> state = unread count; attributes: today, total, last_read, items[]
     items: chas, nove, service, level, title, message (≤300), kopii
  -> excluded from the recorder (attributes exceed 16 KB)

input_button.spovishchennia_prochytano  or  persistent_notification.dismiss
  -> automation notify_log_mark_read -> notify_log.py mark-read -> update_entity
```

Reading model, since the evening of 2026-09-02: **the HA notification drawer
is the primary place** (the owner: "сповіщення саме там мають бути"), and the
journal is its persistent memory.

- Every `notify.*` push is mirrored into the drawer by `notify_log_capture`
  as `persistent_notification.create` with `notification_id: nl_<key>`,
  where `key = md5(sanitised title | sanitised message)`. Three phones give the
  same key, so the drawer shows one entry.
- The same key is stored in the journal row (`--key`). Dismissing that entry
  in the drawer fires `persistent_notification.dismiss` with the `nl_` id, and
  `notify_log_mark_read` marks **that row** read (`mark-read --key`). The
  "mark all read" button still sets the mailbox timestamp for everything and
  calls `persistent_notification.dismiss_all`.
- The drawer is RAM only. `notify_log_restore_on_start` re-creates every
  unread journal item in the drawer two minutes after each start, under the
  same ids, so a power cut no longer empties the list.
- Notifications the journal itself creates (ids starting with `nl_`) are
  excluded from capture; without that guard every push would be journaled
  twice and the restore would loop.

Rows written before 2026-09-02 have no key: they are read only via the button.

## Duplicates

`script.spovistyty_vsikh` sends the same text to three phones, so the database
gets three rows per event. `export` folds consecutive rows with the same title
and message within 20 seconds into one item with `kopii: 3`. The rows stay in
the database; only the view is folded. Keep it that way: the raw rows show
which phone was actually reached.

## Where it shows

- The HA notification drawer (sidebar «Сповіщення»): every push, live and
  restored after restarts — see above.
- Every device tab has its own «Сповіщення» section, separate from
  «Автоматизації» (owner's rule of 2026-09-02: informing and acting are
  different processes). It lists that device's notifying automations as
  toggles with `secondary_info: last-triggered`; the acting ones stay under
  «Автоматизації». New alert automation = one entry in the right section of
  the right tab, plus its line in «Що вони повідомляють».
- The sidebar entry «Сповіщення» (`/spovishchennia-zhurnal/zhurnal`), right
  next to HA's own bell: the history — counts, the mark-read button, the
  folded list with 🔵 for unread, 📱/🔔 for push/panel. Source of truth is
  `board-config/notifications_dashboard.yaml`; on the board it is a
  **storage** dashboard pushed with
  `scripts/lovelace_push.py notifications_dashboard.yaml spovishchennia-zhurnal`
  (WebSocket `lovelace/dashboards/create` + `lovelace/config/save`), because
  registering a YAML dashboard needs a restart the permission classifier
  blocks. Deploy = copy the file, run the script; no reload. It used to be a
  tab of «Пристрої» (`/pristroi-dashboard/alerts`) until the owner asked for
  it in the sidebar on 2026-09-02.
- Overview hero: a line "🔔 N нових сповіщень · журнал", and a badge over the
  page while N > 0.
- `python mcp-server/cli.py notify-log` / MCP `ha_notify_log`: the same export
  for a maintenance session — read it whenever `health` lists problems; the
  board has usually been reporting them for days (nine daily filesystem pushes
  went unread before 2026-09-02).

## Rules for new alerts

1. Call `script.spovistyty_vsikh` (title, message, optional `critical: true`),
   never a list of `notify.mobile_app_*` actions. The phone list lives in one
   place and the journal folds the copies.
2. A watchdog that stays true should push once on detection and then at most
   once a day — the filesystem watchdog is the pattern (`to: on` + daily 09:30
   + after start). A watchdog that flaps (inverter link) needs a `for:` on both
   edges.
3. Anything shown with `persistent_notification.create` also lands in the
   journal automatically; dismissing it marks the journal read. Do not add a
   second mark-read path.
4. Never put text with shell syntax into `shell_command` arguments; the capture
   automation already strips quotes, backticks and `$`. Apostrophes in
   Ukrainian words are the usual victim.
5. The sensor's attributes are the only place the items live in HA; it must
   stay in `recorder.exclude.entities`.

## Known defects (2026-09-03, not fixed yet)

- `notify_log_mark_read` treats **any** `persistent_notification.dismiss`
  whose id does not start with `nl_` as "mark everything read" (its `else`
  branch). The repo has 13 such programmatic dismisses, two of them daily at
  03:50 and 04:00, so alerts from the night are already "read" by morning.
  Until fixed: give every notification you dismiss programmatically an `nl_`
  id or expect the journal to be silently cleared.
- `inverter_zviazok_vidnovleno` is not paired with the "lost" push: it fires
  on `from: unavailable` held for 3 min, which can also happen after a restart
  without any prior loss. The voltage alerts have no hysteresis (three
  "Перенапруга" pushes in 90 min on 03.09). The readiness guard repeats its
  "not ready" push every 6 h while a plug is unavailable (12 a day).

## Script maintenance

`notify_log.py stats` shows size and top titles; `purge --days N` exists but is
manual by design. The script is in `board-config/scripts/` and in
`SYNC_TARGETS`; deploy it like any other file (backup, `.new`, rename), no
reload needed — the next `export` picks it up.
