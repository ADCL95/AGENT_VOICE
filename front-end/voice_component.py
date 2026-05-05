"""
voice_component.py — Streamlit helper for the GPT-4o mini Realtime voice widget.

Renders the front-end/voice.html interface (served by the FastAPI bridge at
``http://localhost:8000``) inside an ``st.components.v1.iframe`` or as a
direct link depending on whether the user wants a full-page or embedded view.

The front-end widget:
  1. Fetches an ephemeral token from ``/voice-token``.
  2. Opens ``wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview``
     using the token (WebSocket protocol headers).
  3. Sends ``session.update`` with VAD, Whisper transcription, and the
     ``query_showroom_agents`` tool that calls our ``/agent`` endpoint.
  4. On a tool call, relays the user query to the multi-agent RAG pipeline
     and sends the answer back as ``function_call_output``.
"""

from __future__ import annotations

import logging

import streamlit as st

logger = logging.getLogger(__name__)

_BRIDGE_URL = "http://localhost:8000"
_VOICE_PAGE_URL = f"{_BRIDGE_URL}/"


def render_voice_widget(height: int = 700, embedded: bool = True) -> None:
    """
    Render the GPT-4o mini Realtime voice widget inside the Streamlit app.

    Parameters
    ----------
    height:
        Pixel height of the embedded iframe.
    embedded:
        If True (default), embed via ``st.components.v1.iframe``.
        If False, show a clickable link to open in a new tab.
    """
    try:
        import streamlit.components.v1 as components  # noqa: PLC0415

        st.markdown(
            """
            <style>
            .rt-widget-header {
                font-size: 0.72rem; color: #b06aff;
                letter-spacing: 0.12em; text-transform: uppercase;
                margin-bottom: 6px;
            }
            .rt-info-chip {
                display: inline-block;
                background: rgba(176,106,255,0.1);
                border: 1px solid rgba(176,106,255,0.25);
                color: #b06aff; border-radius: 20px;
                padding: 2px 10px; font-size: 0.62rem;
                margin-right: 6px; letter-spacing: 0.07em;
            }
            </style>
            <div class="rt-widget-header">🎙️ GPT-4o mini Realtime Voice Agent</div>
            <span class="rt-info-chip">gpt-4o-mini-realtime-preview</span>
            <span class="rt-info-chip">WebSocket · VAD · RAG-enabled</span>
            """,
            unsafe_allow_html=True,
        )

        if embedded:
            components.iframe(src=_VOICE_PAGE_URL, height=height, scrolling=True)
        else:
            st.info(
                f"Voice interface is served at **{_VOICE_PAGE_URL}** — "
                "make sure `python server.py` is running, then open the link in your browser.",
                icon="🎙️",
            )
            st.markdown(
                f'<a href="{_VOICE_PAGE_URL}" target="_blank" rel="noopener noreferrer">'
                '🚀 Open Voice Interface</a>',
                unsafe_allow_html=True,
            )

    except Exception:
        logger.exception(
            "render_voice_widget failed",
            extra={"component": "voice_widget", "step": "render"},
        )
        st.error(
            "⚠️ Could not load the voice widget. "
            f"Ensure the API server is running at {_BRIDGE_URL}."
        )
        st.info(
            "Fallback: open **http://localhost:8000** in your browser and use the "
            "🎙️ Voice (Realtime) tab to connect to the GPT-4o mini Realtime agent.",
            icon="💡",
        )
