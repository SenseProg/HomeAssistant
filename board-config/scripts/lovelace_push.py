#!/userdata/hass/venv/bin/python
"""Зберегти YAML-файл дашборда як storage-дашборд Home Assistant через WebSocket.

Навіщо. Реєстрація YAML-дашборда в configuration.yaml потребує рестарту HA, а
рестарт на цій платі блокує класифікатор дозволів агента. Storage-дашборд
створюється і оновлюється штатним API без рестарту, а джерело правди лишається
файлом у Git. Той самий шлях, яким уже правлять ресурси карток
(lovelace/resources/update) і статистику (recorder/*): API замість .storage.

    lovelace_push.py <файл.yaml> <url_path> [--title T] [--icon mdi:x] [--admin]

url_path storage-дашборда мусить містити дефіс (вимога HA). Якщо дашборда з
таким url_path ще немає - створюється (show_in_sidebar=true). Потім конфіг
файла (усе, крім верхньорівневого title) зберігається як конфіг дашборда.
Токен - /home/forlinx/.ha_token, ніколи не друкується.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import aiohttp
import yaml

TOKEN_FILE = "/home/forlinx/.ha_token"
WS_URL = "ws://localhost:8123/api/websocket"


class WS:
    def __init__(self) -> None:
        self._id = 0

    async def __aenter__(self) -> "WS":
        token = open(TOKEN_FILE, encoding="utf-8").read().strip()
        self.session = aiohttp.ClientSession()
        self.ws = await self.session.ws_connect(WS_URL)
        await self.ws.receive_json()
        await self.ws.send_json({"type": "auth", "access_token": token})
        ok = await self.ws.receive_json()
        if ok.get("type") != "auth_ok":
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


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", help="YAML-файл дашборда; для --dump ставиться '-'")
    p.add_argument("url_path")
    p.add_argument("--title")
    p.add_argument("--icon", default="mdi:view-dashboard")
    p.add_argument("--admin", action="store_true", help="require_admin")
    p.add_argument("--dump", action="store_true", help="лише надрукувати живий конфіг дашборда як JSON (для звірки з файлом)")
    args = p.parse_args()
    if "-" not in args.url_path:
        raise SystemExit("url_path must contain a hyphen")
    if args.dump:
        async with WS() as ws:
            cfg = await ws.call(type="lovelace/config", url_path=args.url_path, force=True)
        print(json.dumps(cfg, ensure_ascii=False, sort_keys=True))
        return 0
    doc = yaml.safe_load(open(args.file, encoding="utf-8"))
    title = args.title or doc.get("title") or args.url_path
    config = {k: v for k, v in doc.items() if k != "title"}
    async with WS() as ws:
        dashboards = await ws.call(type="lovelace/dashboards/list")
        existing = next((d for d in dashboards if d.get("url_path") == args.url_path), None)
        if existing is None:
            created = await ws.call(
                type="lovelace/dashboards/create",
                url_path=args.url_path,
                title=title,
                icon=args.icon,
                show_in_sidebar=True,
                require_admin=args.admin,
                mode="storage",
            )
            print("created dashboard", created.get("id"), args.url_path)
        else:
            print("dashboard exists", existing.get("id"), args.url_path)
        await ws.call(type="lovelace/config/save", url_path=args.url_path, config=config)
        saved = await ws.call(type="lovelace/config", url_path=args.url_path, force=True)
        views = saved.get("views", [])
        print("saved config:", len(views), "views:", [v.get("path") for v in views])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
