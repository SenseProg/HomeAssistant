#!/usr/bin/env python3
"""Add local Wyoming Vosk and enable Ukrainian voice in Claude HomeMate."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import aiohttp

BASE_URL = "http://127.0.0.1:8123"
WS_URL = "ws://127.0.0.1:8123/api/websocket"
TOKEN_PATH = Path("/home/forlinx/.ha_token")
PIPELINE_NAME = "Claude HomeMate"
PIPELINE_ID = "01kz4r9qs1qzp5hsvg9vc7c0m0"
WYOMING_HOST = "127.0.0.1"
WYOMING_PORT = 10300
TTS_ENGINE = "tts.google_translate_en_com"


async def websocket_command(
    ws: aiohttp.ClientWebSocketResponse, message_id: int, command: dict[str, Any]
) -> dict[str, Any]:
    await ws.send_json({"id": message_id, **command})
    while True:
        response = await ws.receive_json(timeout=30)
        if response.get("id") == message_id:
            if not response.get("success"):
                raise RuntimeError(f"WebSocket command failed: {response}")
            return response["result"]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    token = TOKEN_PATH.read_text(encoding="utf-8").strip()
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(
            f"{BASE_URL}/api/config/config_entries/entry"
        ) as response:
            response.raise_for_status()
            entries = await response.json()

        wyoming_entries = [
            entry
            for entry in entries
            if entry.get("domain") == "wyoming"
            and entry.get("title", "").casefold() == "vosk"
        ]

        if not wyoming_entries:
            if not args.apply:
                print("Would add Wyoming Vosk at 127.0.0.1:10300")
                return

            async with session.post(
                f"{BASE_URL}/api/config/config_entries/flow",
                json={"handler": "wyoming", "show_advanced_options": False},
            ) as response:
                response.raise_for_status()
                flow = await response.json()

            if flow.get("type") != "form" or not flow.get("flow_id"):
                raise RuntimeError(f"Unexpected Wyoming flow response: {flow}")

            async with session.post(
                f"{BASE_URL}/api/config/config_entries/flow/{flow['flow_id']}",
                json={"host": WYOMING_HOST, "port": WYOMING_PORT},
            ) as response:
                response.raise_for_status()
                result = await response.json()

            if result.get("type") != "create_entry":
                raise RuntimeError(f"Wyoming integration was not created: {result}")
            print(f"Created Wyoming entry: {result.get('title')}")
            await asyncio.sleep(3)
        else:
            print(f"Wyoming Vosk entry already exists: {wyoming_entries[0]['entry_id']}")

        async with session.ws_connect(WS_URL, heartbeat=30) as ws:
            auth_required = await ws.receive_json(timeout=10)
            if auth_required.get("type") != "auth_required":
                raise RuntimeError(f"Unexpected WebSocket greeting: {auth_required}")
            await ws.send_json({"type": "auth", "access_token": token})
            auth_result = await ws.receive_json(timeout=10)
            if auth_result.get("type") != "auth_ok":
                raise RuntimeError("Home Assistant WebSocket authentication failed")

            stt_engines = await websocket_command(ws, 1, {"type": "stt/engine/list"})
            stt_providers = (
                stt_engines.get("providers", [])
                if isinstance(stt_engines, dict)
                else stt_engines
            )
            if isinstance(stt_providers, list) and all(
                isinstance(engine, str) for engine in stt_providers
            ):
                stt_engine = next(
                    (engine for engine in stt_providers if "vosk" in engine.casefold()),
                    None,
                )
            else:
                stt_engine = next(
                    (
                        engine["engine_id"]
                        for engine in stt_providers
                        if isinstance(engine, dict)
                        and "uk" in engine.get("supported_languages", [])
                    ),
                    None,
                )
            if stt_engine is None:
                raise RuntimeError(f"No Vosk STT engine is available: {stt_engines}")

            tts_engines = await websocket_command(ws, 2, {"type": "tts/engine/list"})
            tts_providers = (
                tts_engines.get("providers", [])
                if isinstance(tts_engines, dict)
                else tts_engines
            )
            tts_engine_ids = {
                engine if isinstance(engine, str) else engine["engine_id"]
                for engine in tts_providers
            }
            if TTS_ENGINE not in tts_engine_ids:
                raise RuntimeError(f"Required TTS engine is unavailable: {TTS_ENGINE}")

            pipelines = await websocket_command(
                ws, 3, {"type": "assist_pipeline/pipeline/list"}
            )
            pipeline_items = (
                pipelines["pipelines"] if isinstance(pipelines, dict) else pipelines
            )
            pipeline = next(
                (
                    item
                    for item in pipeline_items
                    if item.get("id") == PIPELINE_ID
                    or item.get("name") == PIPELINE_NAME
                ),
                None,
            )
            if pipeline is None:
                raise RuntimeError(f"Pipeline not found: {PIPELINE_NAME}")

            desired = {
                **pipeline,
                "stt_engine": stt_engine,
                "stt_language": "uk",
                "tts_engine": TTS_ENGINE,
                "tts_language": "uk",
                "tts_voice": None,
            }
            print(
                json.dumps(
                    {
                        "pipeline": pipeline["name"],
                        "stt_engine": stt_engine,
                        "stt_language": "uk",
                        "tts_engine": TTS_ENGINE,
                        "tts_language": "uk",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            if not args.apply:
                print("Dry run only; use --apply to update the pipeline")
                return

            update_fields = {
                key: desired.get(key)
                for key in (
                    "name",
                    "language",
                    "conversation_engine",
                    "conversation_language",
                    "prefer_local_intents",
                    "stt_engine",
                    "stt_language",
                    "tts_engine",
                    "tts_language",
                    "tts_voice",
                    "wake_word_entity",
                    "wake_word_id",
                )
                if key in desired
            }
            await websocket_command(
                ws,
                4,
                {
                    "type": "assist_pipeline/pipeline/update",
                    "pipeline_id": pipeline["id"],
                    **update_fields,
                },
            )
            print("Claude HomeMate voice pipeline updated")


if __name__ == "__main__":
    asyncio.run(main())
