#!/userdata/hass/venv/bin/python
"""Адміністрування Home Assistant через його власний WebSocket API - на платі.

Усе, що тут є, вже знадобилось 02.09.2026 і робилось із тимчасових скриптів,
які зникли разом із сесією. Жодного читання чи правки .storage: лише штатні
команди API, які ним і володіють (правило 1 скіла home-assistant).

    ha_admin.py orphans [--remove]      автоматизації/скрипти/помічники, що
                                        лишились у реєстрі після видалення з YAML
    ha_admin.py stats-units [--fix]     статистика *_za_tarifom_* без одиниці
                                        (kWh -> None після зміни unit) - перемаркувати
    ha_admin.py resources [--bump URL]  ресурси Lovelace; --bump підняти ?v=N
    ha_admin.py drawer                  що зараз у панелі сповіщень
    ha_admin.py dashboards              список дашбордів (yaml / storage)
    ha_admin.py repairs                 відкриті Repairs

Токен - /home/forlinx/.ha_token, ніколи не друкується.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys

import aiohttp

TOKEN_FILE = "/home/forlinx/.ha_token"
WS_URL = "ws://localhost:8123/api/websocket"
ORPHAN_DOMAINS = ("automation", "script", "input_boolean", "input_datetime", "input_number", "input_select", "input_text")


class WS:
    def __init__(self) -> None:
        self._id = 0

    async def __aenter__(self) -> "WS":
        token = open(TOKEN_FILE, encoding="utf-8").read().strip()
        self.session = aiohttp.ClientSession()
        self.ws = await self.session.ws_connect(WS_URL)
        await self.ws.receive_json()
        await self.ws.send_json({"type": "auth", "access_token": token})
        if (await self.ws.receive_json()).get("type") != "auth_ok":
            raise SystemExit("auth failed")
        return self

    async def __aexit__(self, *exc) -> None:
        await self.ws.close()
        await self.session.close()

    async def call(self, **msg):
        self._id += 1
        msg["id"] = self._id
        await self.ws.send_json(msg)
        while True:
            r = await self.ws.receive_json()
            if r.get("id") == self._id:
                if not r.get("success", True):
                    raise SystemExit("ws error: " + json.dumps(r.get("error"), ensure_ascii=False))
                return r.get("result")


def out(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


async def cmd_orphans(remove: bool) -> None:
    async with WS() as ws:
        reg = await ws.call(type="config/entity_registry/list")
        states = await ws.call(type="get_states")
        st = {s["entity_id"]: s["state"] for s in states}
        alive = {s["entity_id"] for s in states if s["entity_id"].split(".")[0] in ("automation", "script") and s["state"] in ("on", "off")}
        found = []
        for e in reg:
            eid = e["entity_id"]
            if eid.split(".")[0] not in ORPHAN_DOMAINS:
                continue
            if st.get(eid, "missing") not in ("unavailable", "missing") or eid in alive:
                continue
            found.append({"entity_id": eid, "platform": e.get("platform"), "unique_id": e.get("unique_id"), "state": st.get(eid, "missing")})
        removed = []
        if remove:
            for f in found:
                await ws.call(type="config/entity_registry/remove", entity_id=f["entity_id"])
                removed.append(f["entity_id"])
        out({"orphans": found, "count": len(found), "removed": removed})


async def cmd_stats_units(fix: bool) -> None:
    async with WS() as ws:
        meta = await ws.call(type="recorder/get_statistics_metadata")
        rows, bad = [], []
        for m in meta:
            sid = m.get("statistic_id", "")
            if any(k in sid for k in ("za_tarifom", "lichylnyk", "merezha_", "dobovyi", "misiachnyi")):
                unit = m.get("statistics_unit_of_measurement")
                rows.append({"id": sid, "unit": unit, "display": m.get("display_unit_of_measurement"), "class": m.get("unit_class")})
                if unit is None and sid.startswith("sensor."):
                    bad.append(sid)
        fixed = []
        if fix:
            for sid in bad:
                await ws.call(type="recorder/update_statistics_metadata", statistic_id=sid, unit_of_measurement="kWh", unit_class="energy")
                fixed.append(sid)
        out({"rows": rows, "unit_none": bad, "fixed": fixed})


async def cmd_resources(bump: str | None) -> None:
    async with WS() as ws:
        res = await ws.call(type="lovelace/resources")
        if bump:
            target = next((r for r in res if r["url"].split("?")[0] == bump.split("?")[0]), None)
            if not target:
                raise SystemExit("resource not found: " + bump)
            m = re.search(r"[?&]v=(\d+)", target["url"])
            new_url = (re.sub(r"([?&]v=)\d+", lambda x: x.group(1) + str(int(m.group(1)) + 1), target["url"]) if m
                       else target["url"] + ("&" if "?" in target["url"] else "?") + "v=2")
            await ws.call(type="lovelace/resources/update", resource_id=target["id"], res_type="module", url=new_url)
            out({"bumped": target["url"], "to": new_url})
            return
        out([{"id": r["id"], "type": r["type"], "url": r["url"]} for r in res])


async def cmd_drawer() -> None:
    async with WS() as ws:
        r = await ws.call(type="persistent_notification/get")
        out([{"id": n["notification_id"], "title": n.get("title"), "created": n.get("created_at")} for n in r])


async def cmd_dashboards() -> None:
    async with WS() as ws:
        r = await ws.call(type="lovelace/dashboards/list")
        out([{"url_path": d.get("url_path"), "title": d.get("title"), "mode": d.get("mode"), "sidebar": d.get("show_in_sidebar"), "icon": d.get("icon")} for d in r])


async def cmd_repairs() -> None:
    async with WS() as ws:
        r = await ws.call(type="repairs/list_issues")
        out([{"domain": i["domain"], "issue": i["issue_id"], "severity": i["severity"], "created": i["created"][:10], "fixable": i.get("is_fixable")} for i in r.get("issues", [])])


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("orphans"); a.add_argument("--remove", action="store_true")
    b = sub.add_parser("stats-units"); b.add_argument("--fix", action="store_true")
    c = sub.add_parser("resources"); c.add_argument("--bump")
    sub.add_parser("drawer"); sub.add_parser("dashboards"); sub.add_parser("repairs")
    args = p.parse_args()
    if args.cmd == "orphans":
        asyncio.run(cmd_orphans(args.remove))
    elif args.cmd == "stats-units":
        asyncio.run(cmd_stats_units(args.fix))
    elif args.cmd == "resources":
        asyncio.run(cmd_resources(args.bump))
    elif args.cmd == "drawer":
        asyncio.run(cmd_drawer())
    elif args.cmd == "dashboards":
        asyncio.run(cmd_dashboards())
    else:
        asyncio.run(cmd_repairs())
    return 0


if __name__ == "__main__":
    sys.exit(main())
