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

Reading model is a mailbox: one `last_read` timestamp for the whole journal,
everything older counts as read. There is no per-item flag and no need for one.

## Duplicates

`script.spovistyty_vsikh` sends the same text to three phones, so the database
gets three rows per event. `export` folds consecutive rows with the same title
and message within 20 seconds into one item with `kopii: 3`. The rows stay in
the database; only the view is folded. Keep it that way: the raw rows show
which phone was actually reached.

## Where it shows

- `Пристрої → Сповіщення` (`/pristroi-dashboard/alerts`): counts, the
  mark-read button, the folded list with 🔵 for unread, 📱/🔔 for push/panel.
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

## Script maintenance

`notify_log.py stats` shows size and top titles; `purge --days N` exists but is
manual by design. The script is in `board-config/scripts/` and in
`SYNC_TARGETS`; deploy it like any other file (backup, `.new`, rename), no
reload needed — the next `export` picks it up.
