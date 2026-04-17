"""
FastAPI bridge for ``front-end/voice.html`` and other HTTP clients.

**Facade** ``ShowroomAgentPipelineFacade`` runs ``Runner.run`` and maps to the showroom JSON
contract; when ``channel`` is ``voice``, it attaches OpenAI Speech API (TTS) audio fields.

Run: ``python server.py`` from repo root, or ``uvicorn showroom.presentation.server:app``
with ``PYTHONPATH=src``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from agents import Runner, set_default_openai_key
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from showroom.agents.factory import OpenAIAgentSystemFactory
from showroom.agents.response_extract import ShowroomAgentStateExtractor
from showroom.core.settings import AppSettings, get_settings
from showroom.helpers.paths import RepositoryPaths
from showroom.infrastructure.openai_realtime_sessions import OpenAIRealtimeSessionsClient
from showroom.infrastructure.text_to_speech import enrich_response_dict_with_tts
from showroom.rag.application.services.vector_store_service import VectorStoreService

logger = logging.getLogger(__name__)
set_default_openai_key(get_settings().openai_api_key, use_for_tracing=True)


@dataclass
class BridgeRuntimeState:
    """Mutable process state for the HTTP bridge (orchestrator + vector store id)."""

    orchestrator: Any = None
    vector_store_ids: list[str] | None = None


class RealtimeEphemeralTokenClient:
    """
    Application service for /voice-token: delegates HTTP to ``OpenAIRealtimeSessionsClient``.
    """

    __slots__ = ("_settings", "_sessions")

    def __init__(
        self,
        *,
        settings: AppSettings | None = None,
        sessions_client: OpenAIRealtimeSessionsClient | None = None,
    ) -> None:
        self._settings = settings if settings is not None else get_settings()
        self._sessions = sessions_client if sessions_client is not None else OpenAIRealtimeSessionsClient()

    async def fetch_token_payload(self) -> dict[str, str]:
        return await self._sessions.fetch_bridge_token_payload(self._settings)


class ShowroomAgentPipelineFacade:
    """
    Facade over the OpenAI Agents ``Runner`` and ``ShowroomResponse`` normalization.
    """

    __slots__ = ("_orchestrator",)

    def __init__(self, orchestrator: Any) -> None:
        self._orchestrator = orchestrator

    async def execute_turn(self, session_id: str, user_query: str) -> dict[str, Any]:
        formatted = f"[SESSION_ID: {session_id}]\n\n{user_query}"
        try:
            result = await Runner.run(self._orchestrator, formatted)
        except Exception:
            logger.exception("Runner.run failed session_id=%s", session_id)
            raise

        response = ShowroomAgentStateExtractor.default().from_run_result(result, session_id)
        base = response.model_dump()
        return await asyncio.to_thread(enrich_response_dict_with_tts, base)


class VoiceHtmlPageLoader:
    """Loads and patches ``front-end/voice.html`` for same-origin API URLs."""

    __slots__ = ()

    @classmethod
    def load_markup(cls) -> str:
        html_path = RepositoryPaths.root() / "front-end" / "voice.html"
        if not html_path.is_file():
            raise HTTPException(status_code=404, detail="front-end/voice.html not found")
        content = html_path.read_text(encoding="utf-8")
        return content.replace(
            'const SERVER_URL = "http://localhost:8000";',
            'const SERVER_URL = window.location.origin;',
        )


class AgentRequest(BaseModel):
    query: str
    session_id: str = "voice-session"


class ShowroomHttpApplication:
    """
    Composes FastAPI with startup wiring (OpenAI Vector Store + OpenAI Agents SDK).
    """

    __slots__ = ("_state", "_token_client", "_facade", "_realtime_sessions")

    def __init__(self) -> None:
        self._state = BridgeRuntimeState()
        self._realtime_sessions = OpenAIRealtimeSessionsClient()
        self._token_client = RealtimeEphemeralTokenClient(
            sessions_client=self._realtime_sessions,
        )
        self._facade: ShowroomAgentPipelineFacade | None = None

    def build(self) -> FastAPI:
        app = FastAPI(
            title="Aether Motors — Agent Bridge",
            description="Multi-agent RAG pipeline with optional TTS for read-aloud responses",
            version="1.0.0",
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )
        application = self

        @app.on_event("startup")
        async def startup_event() -> None:
            logger.info("Initializing Aether Motors agent system...")
            try:
                application._state.vector_store_ids = await VectorStoreService.default().ensure_async()
                application._state.orchestrator = OpenAIAgentSystemFactory.default().build(
                    application._state.vector_store_ids,
                )
                application._facade = ShowroomAgentPipelineFacade(application._state.orchestrator)
                logger.info("OpenAI Vector Stores ready ids=%s", application._state.vector_store_ids)
            except Exception:
                logger.exception("Startup error while initializing agents or OpenAI Vector Store")
                raise

        @app.get("/", response_class=HTMLResponse)
        async def serve_voice_ui() -> HTMLResponse:
            return HTMLResponse(content=VoiceHtmlPageLoader.load_markup())

        @app.get("/health")
        async def health() -> dict[str, Any]:
            return {
                "status": "ok",
                "agents_ready": application._state.orchestrator is not None,
                "orchestration": "openai-agents",
                "rag_backend": "openai_vector_store",
                "vector_store_ready": application._state.vector_store_ids is not None,
            }

        @app.get("/voice-token")
        async def get_voice_token() -> dict[str, str]:
            try:
                return await application._token_client.fetch_token_payload()
            except httpx.HTTPStatusError as e:
                logger.exception("OpenAI voice-token HTTP error")
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"OpenAI error: {e.response.text}",
                ) from e
            except Exception as e:
                logger.exception("OpenAI voice-token error")
                raise HTTPException(status_code=500, detail=str(e)) from e

        @app.post("/agent")
        async def run_agent(req: AgentRequest) -> dict[str, Any]:
            if application._facade is None:
                raise HTTPException(status_code=503, detail="Agent system not ready yet")
            try:
                return await application._facade.execute_turn(req.session_id, req.query)
            except Exception:
                logger.exception("Agent pipeline error session_id=%s", req.session_id)
                raise HTTPException(status_code=500, detail="Agent error") from None

        return app


app = ShowroomHttpApplication().build()
