"""
Legacy module: the Realtime microphone widget was removed from the product.

Read-aloud uses the same orchestrator graph as text chat; when ``channel`` is ``voice``,
the server attaches OpenAI Speech API (``gpt-4o-mini-tts``) audio in the JSON payload.
"""

from __future__ import annotations

import streamlit as st


def render_voice_widget(height: int = 540) -> None:  # noqa: ARG001
    """No-op placeholder — use chat read-aloud (``channel: voice``) instead."""
    st.info(
        "Voice input is not available. Ask the assistant to read a reply aloud; "
        "the app will play AI-generated speech (OpenAI TTS) when the response uses the voice channel."
    )
