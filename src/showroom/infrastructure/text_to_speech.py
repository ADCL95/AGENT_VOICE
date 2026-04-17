"""
OpenAI Text-to-Speech (Speech API) for read-aloud responses.

Used when ``ShowroomResponse.channel`` is ``voice``: the multi-agent graph still runs
through the orchestrator; this module attaches MP3 bytes for browser or Streamlit playback.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from showroom.core.settings import get_settings
from showroom.infrastructure.openai_client import OpenAIProvider

logger = logging.getLogger(__name__)

# OpenAI usage policy: disclose AI-generated speech to end users.
SYNTHETIC_SPEECH_DISCLOSURE = (
    "The voice you hear is AI-generated and is not a human recording."
)

_MAX_TTS_INPUT_CHARS = 4096


def synthesize_speech_mp3_bytes(text: str) -> bytes:
    """
    Generate MP3 audio bytes for ``text`` using the configured TTS model and voice.
    """
    settings = get_settings()
    payload = (text or "").strip()
    if not payload:
        raise ValueError("TTS input text is empty")
    if len(payload) > _MAX_TTS_INPUT_CHARS:
        payload = payload[: _MAX_TTS_INPUT_CHARS - 3] + "..."

    client = OpenAIProvider.instance()
    kwargs: dict[str, Any] = {
        "model": settings.tts_model,
        "voice": settings.tts_voice,
        "input": payload,
    }
    if settings.tts_instructions.strip():
        kwargs["instructions"] = settings.tts_instructions.strip()

    response = client.audio.speech.create(**kwargs)

    content = getattr(response, "content", None)
    if content is not None:
        return content if isinstance(content, (bytes, bytearray)) else bytes(content)
    read_fn = getattr(response, "read", None)
    if callable(read_fn):
        data = read_fn()
        return data if isinstance(data, (bytes, bytearray)) else bytes(data)
    raise TypeError("Unexpected speech API response shape")


def synthesize_speech_mp3_base64(text: str) -> str:
    return base64.b64encode(synthesize_speech_mp3_bytes(text)).decode("ascii")


SHOWROOM_RESPONSE_KEYS = ("message_agent", "channel", "intent", "session_id")


def showroom_response_contract_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """Return only the four canonical ``ShowroomResponse`` fields (for JSON viewers and logs)."""
    return {k: payload[k] for k in SHOWROOM_RESPONSE_KEYS if k in payload}


def enrich_response_dict_with_tts(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Return the showroom contract (four keys) plus, when ``channel == "voice"``, a nested
    ``voice`` object for playback — never ``tts_disclosure``, ``audio_mp3_base64``, or
    ``audio_mime_type`` at the top level.

    ``voice`` shape:
      - success: ``{"audio": "<base64>", "format": "audio/mpeg"}``
      - failure: ``{"error": "<message>"}``

    UI layers should show ``SYNTHETIC_SPEECH_DISCLOSURE`` as plain copy, not inside this JSON.
    """
    base = showroom_response_contract_dict(payload)
    if base.get("channel") != "voice":
        return base
    text = base.get("message_agent") or ""
    out = dict(base)
    try:
        out["voice"] = {
            "audio": synthesize_speech_mp3_base64(str(text)),
            "format": "audio/mpeg",
        }
    except Exception:
        logger.exception(
            "TTS enrichment failed",
            extra={"component": "tts", "session_id": base.get("session_id")},
        )
        out["voice"] = {
            "error": "Text-to-speech is temporarily unavailable; please read the text reply.",
        }
    return out
