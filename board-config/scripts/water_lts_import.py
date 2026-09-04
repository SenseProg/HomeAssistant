#!/userdata/hass/venv/bin/python
"""Імпорт історії води свердловини в довгострокову статистику sensor.sverdlovina_voda_m3.

Навіщо. Сенсор sensor.sverdlovina_voda_m3 (template, total_increasing, m³)
створено 03.09.2026, а вода рахувалась з 21.08 - з інтегратора енергії насоса.
LTS інтегратора (погодинні суми кВт·год) живе з 21.08; помножена на
коефіцієнт вона і є історією води. Так графіки «30 днів» і «рік» отримують
минуле одразу, а не через місяць.

Той самий прийом, що в docs/cost-history-recalc.md: recorder/import_statistics
для минулого, потім recorder/adjust_sum_statistics, щоб живі суми сенсора
продовжили з тієї ж точки без розриву.

    water_lts_import.py import [--days 40] [--coef 0.802] [--dry-run]
    water_lts_import.py adjust            # після першої живої години сенсора
    water_lts_import.py recalibrate [--days 40]   # після зміни коефіцієнта

recalibrate (04.09.2026): коефіцієнт міняється після кожного показника
механічного лічильника, а сенсор води - це (E + offset) × k, тож у ту мить він
стрибає (04.09: 5,650 → 7,559 м³, +1,9 м³ «спожито» за одну годину). Команда
переписує погодинну історію новим k (той самий import) і вирівнює живу
5-хвилинну суму з останньою імпортованою годиною, щоб стрибок не потрапив у
добові й місячні графіки. Викликається автоматизацією калібрування.

Ключ: energy_offset_kwh з calibration журналу показників (вода від контрольної
точки = (E + offset) × коефіцієнт, як у самому сенсорі).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
import urllib.request

import aiohttp

TOKEN_FILE = "/home/forlinx/.ha_token"
WS_URL = "ws://localhost:8123/api/websocket"
SRC = "sensor.t34_smart_plug_nasos_sverdlovini_spozhito"
DST = "sensor.sverdlovina_voda_m3"


class WS:
    def __init__(self) -> None:
        self._id = 0

    async def __aenter__(self):
        token = open(TOKEN_FILE, encoding="utf-8").read().strip()
        self.session = aiohttp.ClientSession()
        self.ws = await self.session.ws_connect(WS_URL)
        await self.ws.receive_json()
        await self.ws.send_json({"type": "auth", "access_token": token})
        if (await self.ws.receive_json()).get("type") != "auth_ok":
            raise SystemExit("auth failed")
        return self

    async def __aexit__(self, *exc):
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


def rest_state(entity_id: str) -> dict:
    token = open(TOKEN_FILE, encoding="utf-8").read().strip()
    req = urllib.request.Request("http://localhost:8123/api/states/" + entity_id, headers={"Authorization": "Bearer " + token})
    return json.load(urllib.request.urlopen(req, timeout=30))


async def cmd_import(days: int, coef: float | None, dry: bool) -> None:
    cal = (rest_state("sensor.zhurnal_pokaznykiv_vody").get("attributes") or {}).get("calibration") or {}
    offset = float(cal.get("energy_offset_kwh", 0) or 0)
    k = coef if coef is not None else float(rest_state("input_number.sverdlovina_koefitsiient_vodi")["state"])
    start = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).replace(minute=0, second=0, microsecond=0)
    async with WS() as ws:
        rows = (await ws.call(type="recorder/statistics_during_period", start_time=start.isoformat(),
                              statistic_ids=[SRC], period="hour", types=["state", "sum"])).get(SRC, [])
        if not rows:
            raise SystemExit("no LTS rows for " + SRC)
        # Вода від контрольної точки = (E + offset) × k; сума статистики = вода наростаючим підсумком
        stats = []
        prev_sum = None
        for r in rows:
            e = r.get("state")
            if e is None:
                continue
            water = max(e + offset, 0.0) * k
            stats.append({"start": dt.datetime.fromtimestamp(r["start"] / 1000, dt.timezone.utc).isoformat(),
                          "state": round(water, 3), "sum": round(water, 3)})
        print(f"rows: {len(stats)}, offset={offset}, coef={k}, first={stats[0]['start'][:16]} last={stats[-1]['start'][:16]} last_sum={stats[-1]['sum']}")
        if dry:
            print(json.dumps(stats[-3:], ensure_ascii=False))
            return None
        await ws.call(type="recorder/import_statistics",
                      metadata={"has_mean": False, "has_sum": True, "name": None, "source": "recorder",
                                "statistic_id": DST, "unit_of_measurement": "m³"},
                      stats=stats)
        print("imported", len(stats), "hourly rows into", DST)
        return stats[-1]


async def cmd_adjust() -> None:
    """Вирівняти живу суму сенсора з імпортованою: після першої живої години
    sum сенсора починається з нуля, а імпорт закінчується на X м³ - додаємо X."""
    async with WS() as ws:
        now = dt.datetime.now(dt.timezone.utc)
        hourly = (await ws.call(type="recorder/statistics_during_period", start_time=(now - dt.timedelta(days=60)).isoformat(),
                                statistic_ids=[DST], period="hour", types=["sum"])).get(DST, [])
        short = (await ws.call(type="recorder/statistics_during_period", start_time=(now - dt.timedelta(hours=6)).isoformat(),
                               statistic_ids=[DST], period="5minute", types=["sum"])).get(DST, [])
        # Імпорт пише лише погодинну таблицю; живий сенсор починає з 5-хвилинної,
        # і його перша сума - нуль. Розрив = остання імпортована сума мінус перша
        # жива; adjust_sum_statistics додає його всім рядкам від тієї миті в
        # обох таблицях, тож погодинний рядок, який скомпілюється пізніше,
        # успадкує вже вирівняну суму.
        imported = [r for r in hourly if r.get("sum") is not None]
        live = [r for r in short if r.get("sum") is not None]
        if not imported or not live:
            raise SystemExit(f"nothing to compare: hourly={len(imported)} short-term={len(live)}")
        last_imported = imported[-1]["sum"]
        first_live = live[0]
        if first_live["sum"] < last_imported - 0.05:
            delta = round(last_imported - first_live["sum"], 3)
            when = dt.datetime.fromtimestamp(first_live["start"] / 1000, dt.timezone.utc).isoformat()
            print(f"gap at {when[:16]}: imported {last_imported} -> live {first_live['sum']}, adjusting by +{delta}")
            await ws.call(type="recorder/adjust_sum_statistics", statistic_id=DST, start_time=when,
                          adjustment=delta, adjustment_unit_of_measurement="m³")
            print("adjusted")
            return
        print(f"no gap: imported {last_imported}, first live {first_live['sum']}")


async def cmd_recalibrate(days: int) -> None:
    """Переписати історію поточним k і вирівняти живу суму (див. docstring)."""
    last_row = await cmd_import(days, None, False)
    async with WS() as ws:
        now = dt.datetime.now(dt.timezone.utc)
        # import_statistics лише ставить задачу в чергу recorder - рядки лягають
        # у базу за кілька секунд; читати їх одразу означає побачити старі суми.
        hourly = []
        for _ in range(30):
            hourly = (await ws.call(type="recorder/statistics_during_period", start_time=(now - dt.timedelta(days=3)).isoformat(),
                                    statistic_ids=[DST], period="hour", types=["state", "sum"])).get(DST, [])
            got = [r for r in hourly if r.get("sum") is not None]
            if last_row and got and abs(got[-1]["sum"] - last_row["sum"]) < 0.002:
                break
            await asyncio.sleep(2)
        else:
            raise SystemExit("import did not land in the recorder within 60 s - not aligning")
        short = (await ws.call(type="recorder/statistics_during_period", start_time=(now - dt.timedelta(hours=3)).isoformat(),
                               statistic_ids=[DST], period="5minute", types=["sum"])).get(DST, [])
        imported = [r for r in hourly if r.get("sum") is not None and r.get("state") is not None]
        live = [r for r in short if r.get("sum") is not None]
        if not imported or not live:
            raise SystemExit(f"nothing to align: hourly={len(imported)} short-term={len(live)}")
        last = imported[-1]
        # Реальна вода після кінця останньої повної години - різниця між живим
        # станом сенсора зараз і станом на кінець тієї години (обидва з поточним k).
        state_now = float(rest_state(DST)["state"])
        target = last["sum"] + (state_now - last["state"])
        cur = live[-1]
        delta = round(target - cur["sum"], 3)
        when = dt.datetime.fromtimestamp(cur["start"] / 1000, dt.timezone.utc).isoformat()
        print(f"align: imported last hour sum={last['sum']:.3f} state={last['state']:.3f}, live now={state_now:.3f}, "
              f"short-term sum={cur['sum']:.3f} at {when[:16]} -> adjust {delta:+.3f}")
        if abs(delta) < 0.005:
            print("no adjustment needed")
            return
        await ws.call(type="recorder/adjust_sum_statistics", statistic_id=DST, start_time=when,
                      adjustment=delta, adjustment_unit_of_measurement="m³")
        print("adjusted")


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("import"); a.add_argument("--days", type=int, default=40); a.add_argument("--coef", type=float); a.add_argument("--dry-run", action="store_true")
    sub.add_parser("adjust")
    r = sub.add_parser("recalibrate"); r.add_argument("--days", type=int, default=40)
    args = p.parse_args()
    if args.cmd == "import":
        asyncio.run(cmd_import(args.days, args.coef, args.dry_run))
    elif args.cmd == "recalibrate":
        asyncio.run(cmd_recalibrate(args.days))
    else:
        asyncio.run(cmd_adjust())
    return 0


if __name__ == "__main__":
    sys.exit(main())
