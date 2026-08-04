"""Authenticated HTTP access to private Claude voice recordings."""

from __future__ import annotations

import base64
import binascii
from pathlib import Path

from aiohttp import web

from homeassistant.components.http import HomeAssistantView

from .const import VOICE_RECORDING_DIR


def encode_recording_id(path: Path) -> str:
    """Encode a relative recording path as a URL-safe opaque id."""
    relative = path.relative_to(Path(VOICE_RECORDING_DIR)).as_posix()
    return base64.urlsafe_b64encode(relative.encode()).decode().rstrip("=")


def recording_path(recording_id: str) -> Path | None:
    """Resolve an opaque recording id without allowing path traversal."""
    try:
        padding = "=" * (-len(recording_id) % 4)
        relative_text = base64.urlsafe_b64decode(recording_id + padding).decode()
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None

    root = Path(VOICE_RECORDING_DIR).resolve()
    candidate = (root / relative_text).resolve()
    if not candidate.is_relative_to(root) or candidate.suffix.casefold() != ".wav":
        return None
    return candidate


class VoiceRecordingView(HomeAssistantView):
    """Serve one archived WAV to an authenticated user or signed URL."""

    name = "api:claude_code_conversation:voice_recording"
    url = "/api/claude_code_conversation/voice-recording/{recording_id}"
    requires_auth = True

    async def get(self, request: web.Request, recording_id: str) -> web.StreamResponse:
        """Return a private WAV recording."""
        path = recording_path(recording_id)
        if path is None or not path.is_file():
            raise web.HTTPNotFound()

        response = web.FileResponse(path)
        response.content_type = "audio/wav"
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Content-Disposition"] = f'inline; filename="{path.name}"'
        return response
