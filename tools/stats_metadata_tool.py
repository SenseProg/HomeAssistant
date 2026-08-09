"""Robota zi statystykoyu HA cherez WebSocket API.

Rezhymy:
  inspect  - pokazaty metadani ta pershi/ostanni tochky dlia problemnykh sensoriv
  fix      - onovyty unit_of_measurement u metadanykh (stari zapysy zberihayutsia)

Zapuskaty venvom HA:
  /home/forlinx/hass-venv-314/bin/python stats_tool.py inspect
"""
import asyncio
import json
import sys

import aiohttp

TOKEN_PATH = "/home/forlinx/.ha_token"
WS_URL = "ws://127.0.0.1:8123/api/websocket"

IDS = [
    "sensor.boiler_sogodni",
    "sensor.merezha_dobovyi_nich",
    "sensor.merezha_misiachnyi_nich",
    "sensor.merezha_za_tarifom_nich",
    "sensor.nasos_za_tarifom_den",
    "sensor.pidloha_1_za_tarifom_den",
    "sensor.terneo_1_tepla_pidloga_1_sogodni",
    "sensor.zariadka_za_tarifom_den",
]

TARGET_UNIT = "kWh"


class Client:
    def __init__(self, ws):
        self.ws = ws
        self._id = 0

    async def call(self, payload):
        self._id += 1
        payload = dict(payload, id=self._id)
        await self.ws.send_json(payload)
        while True:
            msg = await self.ws.receive_json()
            if msg.get("id") == self._id and msg.get("type") == "result":
                if not msg.get("success", False):
                    return {"__error__": msg.get("error")}
                return msg.get("result")


async def connect(session):
    ws = await session.ws_connect(WS_URL)
    await ws.receive_json()  # auth_required
    await ws.send_json({"type": "auth", "access_token": open(TOKEN_PATH).read().strip()})
    ack = await ws.receive_json()
    if ack.get("type") != "auth_ok":
        raise SystemExit("AUTH FAILED: %s" % ack)
    return ws


async def inspect(c):
    meta = await c.call({"type": "recorder/get_statistics_metadata", "statistic_ids": IDS})
    if isinstance(meta, dict) and "__error__" in meta:
        print("METADATA ERROR:", meta["__error__"])
        return
    by_id = {m["statistic_id"]: m for m in meta}
    print("%-46s %-12s %-8s %-8s %s" % ("STATISTIC_ID", "STAT_UNIT", "has_sum", "has_mean", "SOURCE"))
    for sid in IDS:
        m = by_id.get(sid)
        if not m:
            print("%-46s %s" % (sid[7:], "NEMAYE METADANYKH"))
            continue
        print("%-46s %-12s %-8s %-8s %s" % (
            sid[7:], str(m.get("unit_of_measurement")), m.get("has_sum"),
            m.get("has_mean"), m.get("source")))

    print("\n--- ostanni tochky (sum) ta potochnyi stan sensora ---")
    stats = await c.call({
        "type": "recorder/statistics_during_period",
        "start_time": "2026-08-01T00:00:00+03:00",
        "statistic_ids": IDS,
        "period": "day",
    })
    if isinstance(stats, dict) and "__error__" in stats:
        print("STATS ERROR:", stats["__error__"])
        return
    states = await c.call({"type": "get_states"})
    st_by_id = {s["entity_id"]: s for s in states} if isinstance(states, list) else {}
    for sid in IDS:
        pts = stats.get(sid) or []
        last = pts[-1] if pts else None
        cur = st_by_id.get(sid, {})
        print("%-46s tochok=%-4s last_sum=%-12s last_state=%-12s zaraz=%s %s" % (
            sid[7:], len(pts),
            round(last["sum"], 2) if last and last.get("sum") is not None else "-",
            round(last["state"], 2) if last and last.get("state") is not None else "-",
            cur.get("state", "-"),
            cur.get("attributes", {}).get("unit_of_measurement", "-")))


async def fix(c):
    # unit_class obovyazkovyi: bez nyoho HA prosto ihnoruye novu odynytsyu.
    print("Onovlyuyu metadani: unit=%s, unit_class=energy" % TARGET_UNIT)
    for sid in IDS:
        res = await c.call({
            "type": "recorder/update_statistics_metadata",
            "statistic_id": sid,
            "unit_class": "energy",
            "unit_of_measurement": TARGET_UNIT,
        })
        err = res.get("__error__") if isinstance(res, dict) else None
        print("  %-46s %s" % (sid[7:], "ERROR: %s" % err if err else "OK"))


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "inspect"
    async with aiohttp.ClientSession() as session:
        ws = await connect(session)
        c = Client(ws)
        if mode == "inspect":
            await inspect(c)
        elif mode == "fix":
            await fix(c)
        else:
            print("nevidomyi rezhym:", mode)
        await ws.close()


asyncio.run(main())
