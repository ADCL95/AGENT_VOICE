"""
HTTP adapter for OpenAI ``POST /v1/realtime/sessions``.

Decouples URL, headers, and payloads from presentation and Streamlit UI code.
"""

from __future__ import annotations

from typing import Any

import httpx

from showroom.core.settings import AppSettings


class OpenAIRealtimeSessionsClient:
    """
    Infrastructure client for creating Realtime session credentials.

    Used by the FastAPI bridge (minimal payload) and the Streamlit voice widget (full payload).
    """

    __slots__ = ("_timeout", "_base_url")

    _DEFAULT_URL = "https://api.openai.com/v1/realtime/sessions"

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        base_url: str | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._base_url = base_url or self._DEFAULT_URL

    def _headers(self, settings: AppSettings) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }

    async def fetch_bridge_token_payload(self, settings: AppSettings) -> dict[str, str]:
        """
        Minimal session body for the voice.html bridge (token + model echo).

        Matches the previous FastAPI ``/voice-token`` contract.
        """
        body: dict[str, Any] = {
            "model": settings.model_realtime,
            "voice": "alloy",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                self._base_url,
                headers=self._headers(settings),
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "token": data["client_secret"]["value"],
                "model": settings.model_realtime,
            }

    def fetch_streamlit_widget_client_secret_sync(self, settings: AppSettings) -> str:
        """
        Full session body for the embedded Streamlit voice widget (modalities, VAD, etc.).

        Returns only the ``client_secret.value`` string for HTML injection.
        """
        body: dict[str, Any] = {
            "model": settings.model_realtime,
            "voice": "alloy",
            "modalities": ["text", "audio"],
            "instructions": (
                "You are a helpful voice assistant for the Aether Motors Virtual Showroom. "
                "Answer questions about our luxury electric vehicles, showroom layouts, and purchasing options. "
                "Be concise, warm, and professional."
            ),
            "input_audio_transcription": {"model": "whisper-1"},
            "turn_detection": {"type": "server_vad"},
        }
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(
                self._base_url,
                headers=self._headers(settings),
                json=body,
            )
            resp.raise_for_status()
            return str(resp.json()["client_secret"]["value"])


class VoiceWidgetEphemeralCredentialsIssuer:
    """
    Facade for Streamlit: obtains a client secret for the embedded voice widget.

    Delegates to ``OpenAIRealtimeSessionsClient`` (same decoupling as the FastAPI bridge).
    """

    __slots__ = ("_sessions",)

    def __init__(self, sessions_client: OpenAIRealtimeSessionsClient | None = None) -> None:
        self._sessions = sessions_client or OpenAIRealtimeSessionsClient()

    def issue_client_secret_sync(self, settings: AppSettings) -> str:
        return self._sessions.fetch_streamlit_widget_client_secret_sync(settings)
