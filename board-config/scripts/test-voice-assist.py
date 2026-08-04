#!/usr/bin/env python3
"""End-to-end synthetic voice test for the Claude HomeMate Assist pipeline."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any

import aiohttp

BASE_URL = "http://127.0.0.1:8123"
WS_URL = "ws://127.0.0.1:8123/api/websocket"
TOKEN_PATH = Path("/home/forlinx/.ha_token")
PIPELINE_ID = "01kz4r9qs1qzp5hsvg9vc7c0m0"
TEST_TEXT = "Скажи одним реченням, що голосовий режим працює"


async def authenticate(
    session: aiohttp.ClientSession, token: str
) -> aiohttp.ClientWebSocketResponse:
    ws = await session.ws_connect(WS_URL, heartbeat=30)
    greeting = await ws.receive_json(timeout=10)
    if greeting.get("type") != "auth_required":
        raise RuntimeError(f"Unexpected greeting: {greeting}")
    await ws.send_json({"type": "auth", "access_token": token})
    result = await ws.receive_json(timeout=10)
    if result.get("type") != "auth_ok":
        raise RuntimeError("WebSocket authentication failed")
    return ws


async def collect_run(
    ws: aiohttp.ClientWebSocketResponse, message_id: int
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    while True:
        message = await ws.receive(timeout=120)
        if message.type != aiohttp.WSMsgType.TEXT:
            continue
        payload = json.loads(message.data)
        if payload.get("id") != message_id:
            continue
        if payload.get("type") == "result" and not payload.get("success"):
            raise RuntimeError(f"Pipeline failed to start: {payload}")
        if payload.get("type") != "event":
            continue
        event = payload["event"]
        events.append(event)
        if event.get("type") in ("run-end", "error"):
            return events


def event_data(events: list[dict[str, Any]], event_type: str) -> dict[str, Any]:
    for event in events:
        if event.get("type") == event_type:
            return event.get("data") or {}
    raise RuntimeError(f"Missing pipeline event: {event_type}; got {events}")


async def main() -> None:
    token = TOKEN_PATH.read_text(encoding="utf-8").strip()
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession(headers=headers) as session:
        # Generate clean Ukrainian reference speech through the configured TTS.
        tts_ws = await authenticate(session, token)
        await tts_ws.send_json(
            {
                "id": 10,
                "type": "assist_pipeline/run",
                "start_stage": "tts",
                "end_stage": "tts",
                "pipeline": PIPELINE_ID,
                "input": {"text": TEST_TEXT},
            }
        )
        tts_events = await collect_run(tts_ws, 10)
        await tts_ws.close()
        tts_output = event_data(tts_events, "tts-end")["tts_output"]
        audio_url = tts_output["url"]
        if audio_url.startswith("/"):
            audio_url = BASE_URL + audio_url

        async with session.get(audio_url) as response:
            response.raise_for_status()
            encoded_audio = await response.read()

        with tempfile.TemporaryDirectory(prefix="homemate-voice-") as temp_dir:
            encoded_path = Path(temp_dir) / "reference-audio"
            pcm_path = Path(temp_dir) / "reference.pcm"
            encoded_path.write_bytes(encoded_audio)
            subprocess.run(
                [
                    "/usr/bin/ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(encoded_path),
                    "-f",
                    "s16le",
                    "-acodec",
                    "pcm_s16le",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    str(pcm_path),
                ],
                check=True,
            )
            pcm_audio = pcm_path.read_bytes()

        # Feed the speech back through STT -> Claude -> TTS.
        assist_ws = await authenticate(session, token)
        await assist_ws.send_json(
            {
                "id": 20,
                "type": "assist_pipeline/run",
                "start_stage": "stt",
                "end_stage": "tts",
                "pipeline": PIPELINE_ID,
                "input": {"sample_rate": 16000},
                "timeout": 120,
            }
        )

        # A new websocket connection receives binary handler id 1.
        while True:
            message = await assist_ws.receive_json(timeout=20)
            if message.get("id") != 20:
                continue
            if message.get("type") == "result":
                if not message.get("success"):
                    raise RuntimeError(f"Voice pipeline failed to start: {message}")
                break

        for offset in range(0, len(pcm_audio), 3200):
            await assist_ws.send_bytes(bytes([1]) + pcm_audio[offset : offset + 3200])
        await assist_ws.send_bytes(bytes([1]))
        events = await collect_run(assist_ws, 20)
        await assist_ws.close()

        if any(event.get("type") == "error" for event in events):
            raise RuntimeError(f"Voice pipeline error: {events}")

        stt_output = event_data(events, "stt-end")["stt_output"]
        intent_output = event_data(events, "intent-end")["intent_output"]
        final_tts = event_data(events, "tts-end")["tts_output"]
        speech = (
            intent_output.get("response", {})
            .get("speech", {})
            .get("plain", {})
            .get("speech", "")
        )
        print(
            json.dumps(
                {
                    "input_text": TEST_TEXT,
                    "transcript": stt_output.get("text"),
                    "assistant_response": speech,
                    "tts_url": final_tts.get("url"),
                    "tts_mime_type": final_tts.get("mime_type"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
