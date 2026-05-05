"""
HTTP adapter for OpenAI ``POST /v1/realtime/sessions``.

Decouples URL, headers, and payloads from presentation and Streamlit UI code.

The Realtime model (``gpt-4o-mini-realtime-preview``) is configured with:
  - Server VAD turn detection
  - Whisper transcription
  - A ``query_showroom_agents`` function tool so the voice agent can delegate
    factual queries to the full multi-agent RAG pipeline at runtime.
"""

from __future__ import annotations

from typing import Any

import httpx

from showroom.core.settings import AppSettings

# System instructions injected into every Realtime session.
# The voice agent uses ``query_showroom_agents`` for factual lookups and
# falls back to direct speech for greetings / conversational exchanges.
_REALTIME_INSTRUCTIONS = (
    "You are the Aether Motors voice assistant.\n"
    "For every user question: ALWAYS call `query_showroom_agents` first.\n"
    "Your final answer must use ONLY tool output content. Do not invent details.\n"
    "When tool output includes VERBATIM_START and VERBATIM_END markers, read ONLY the enclosed text.\n"
    "Do not summarize, rephrase, reorder, add, or remove any detail from that marked text.\n"
    "When the tool includes identifiers or numeric facts (layout IDs, capacities, prices, dimensions), "
    "repeat them exactly.\n"
    "If the user asks for a human advisor, confirm escalation clearly."
)

# Tool schema registered on every Realtime session so the model can call the
# backend multi-agent pipeline for factual retrieval.
_QUERY_AGENTS_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "query_showroom_agents",
    "description": (
        "Query the Aether Motors multi-agent RAG system. "
        "Use for vehicle specs, showroom layouts, pricing, purchasing options, "
        "or any factual question that requires retrieval from the knowledge base. "
        "Pass the user's question verbatim or slightly clarified."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "The user's question or request to look up in the "
                    "Aether Motors knowledge base."
                ),
            }
        },
        "required": ["query"],
    },
}


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

        The front-end overrides the full session config via ``session.update``
        after the WebSocket opens; we only need the ephemeral token here.
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

        Includes the ``query_showroom_agents`` tool so the voice agent can
        delegate to the multi-agent RAG pipeline.
        Returns only the ``client_secret.value`` string for HTML injection.
        """
        body: dict[str, Any] = {
            "model": settings.model_realtime,
            "voice": "alloy",
            "modalities": ["text", "audio"],
            "instructions": _REALTIME_INSTRUCTIONS,
            "input_audio_transcription": {"model": "whisper-1"},
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 350,
            },
            "tools": [_QUERY_AGENTS_TOOL],
            "tool_choice": "required",
            "max_response_output_tokens": 320,
            "temperature": 0.1,
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
