"""
app.py — Streamlit UI for the Aether Motors AI Virtual Showroom

Features:
  - Multi-agent conversational AI (OpenAI Agents SDK orchestrator + four specialists)
  - Full conversation memory across turns (session-scoped message history)
  - Intent classification badges with color coding
  - JSON response contract viewer (expandable)
  - Channel indicators (text / voice / escalation)
  - Session management with clear/reset
  - Graceful error handling — one failing turn never kills the session
"""

import logging
import streamlit as st
import asyncio
import base64
import uuid
import json
import nest_asyncio

# Must be applied BEFORE any async calls — patches event loop for Streamlit compatibility
nest_asyncio.apply()

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
for _p in (_SRC, _REPO_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from showroom.agents.factory import OpenAIAgentSystemFactory
from showroom.agents.response_extract import ShowroomAgentStateExtractor
from showroom.domain.schemas import ShowroomResponse
from showroom.rag.application.services.vector_store_service import VectorStoreService
from agents import Runner, set_default_openai_key
from showroom.core.settings import get_settings
from showroom.infrastructure.text_to_speech import (
    SYNTHETIC_SPEECH_DISCLOSURE,
    enrich_response_dict_with_tts,
    showroom_response_contract_dict,
)

set_default_openai_key(get_settings().openai_api_key, use_for_tracing=True)

logger = logging.getLogger(__name__)

# ─── Page Configuration ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="Aether Motors — AI Showroom",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS — Luxury Dark Theme ──────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background: linear-gradient(160deg, #080810 0%, #0d0d20 50%, #0a0a18 100%);
    color: #e0e0e8;
}

/* Header */
.aether-header {
    text-align: center;
    padding: 1.5rem 0 0.5rem 0;
}
.aether-logo {
    font-size: 2.2rem;
    font-weight: 700;
    letter-spacing: 0.25em;
    background: linear-gradient(90deg, #e8b84b, #ffd700, #e8b84b);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    text-transform: uppercase;
}
.aether-tagline {
    font-size: 0.72rem;
    color: #666680;
    letter-spacing: 0.3em;
    text-transform: uppercase;
    margin-top: 4px;
    margin-bottom: 1.5rem;
}

/* Intent badges */
.intent-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.65rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-top: 6px;
}
.badge-product_info     { background:#0d2040; color:#5aadff; border:1px solid #2060a0; }
.badge-space_analysis   { background:#0a2616; color:#4dcc80; border:1px solid #1a6640; }
.badge-purchase_intent  { background:#302000; color:#ffc040; border:1px solid #806000; }
.badge-voice_request    { background:#1e0d36; color:#b06aff; border:1px solid #5020a0; }
.badge-escalation       { background:#300d0d; color:#ff6060; border:1px solid #802020; }
.badge-unknown          { background:#1a1a2a; color:#8888aa; border:1px solid #404060; }

/* Sidebar info cards */
.info-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,215,0,0.15);
    border-radius: 8px;
    padding: 10px 14px;
    margin-bottom: 10px;
}
.info-label {
    font-size: 0.62rem;
    color: #66667a;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    margin-bottom: 3px;
}
.info-value {
    font-size: 0.9rem;
    color: #ffd700;
    font-weight: 600;
}

/* Welcome screen */
.welcome-box {
    text-align: center;
    padding: 3rem 2rem;
    border: 1px solid rgba(255,215,0,0.1);
    border-radius: 16px;
    background: rgba(255,255,255,0.02);
    margin: 2rem auto;
    max-width: 640px;
}
.welcome-icon { font-size: 3rem; }
.welcome-title { font-size: 1.3rem; color: #ffd700; margin: 1rem 0 0.5rem 0; font-weight: 600; }
.welcome-sub { font-size: 0.85rem; color: #888898; margin-bottom: 1.5rem; }
.welcome-examples { font-size: 0.78rem; color: #555568; }
.welcome-example {
    display: inline-block;
    background: rgba(255,215,0,0.06);
    border: 1px solid rgba(255,215,0,0.12);
    border-radius: 20px;
    padding: 4px 12px;
    margin: 4px;
    cursor: default;
}

/* Agent pipeline display */
.agent-node {
    font-size: 0.78rem;
    padding: 4px 0;
    color: #aaaacc;
}
.agent-node-active { color: #ffd700; }

/* Escalation / voice banners */
.banner-voice {
    background: rgba(100,40,160,0.2);
    border: 1px solid rgba(150,80,255,0.4);
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 0.82rem;
    color: #b06aff;
    margin-top: 6px;
}
.banner-escalation {
    background: rgba(120,20,20,0.2);
    border: 1px solid rgba(255,80,80,0.4);
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 0.82rem;
    color: #ff8080;
    margin-top: 6px;
}
</style>
""", unsafe_allow_html=True)


# ─── Constants ────────────────────────────────────────────────────────────────

INTENT_META = {
    "product_info":    {"emoji": "🚗", "label": "Product Info",    "css": "product_info"},
    "space_analysis":  {"emoji": "📐", "label": "Space Analysis",  "css": "space_analysis"},
    "purchase_intent": {"emoji": "💳", "label": "Purchase Intent", "css": "purchase_intent"},
    "voice_request":   {"emoji": "🎙️", "label": "Voice Request",   "css": "voice_request"},
    "escalation":      {"emoji": "👤", "label": "Escalation",      "css": "escalation"},
    "unknown":         {"emoji": "💬", "label": "Unknown",         "css": "unknown"},
}

CHANNEL_ICON = {"text": "💬", "voice": "🔊", "escalation": "🔴"}

AGENTS_PIPELINE = [
    ("🧠", "OrchestratorAgent",  "Classifies & routes"),
    ("🚗", "ProductInfoAgent",   "Vehicle specs & pricing"),
    ("📐", "SpaceAnalysisAgent", "Showroom layouts"),
    ("💳", "PurchaseIntentAgent","Financing & orders"),
    ("👤", "EscalationAgent",    "Human handoff"),
]


# ─── Session State Initialization ─────────────────────────────────────────────

def init_session() -> None:
    """Initialize all session state variables on first load."""
    defaults = {
        "session_id":    f"SES-{str(uuid.uuid4())[:8].upper()}",
        "messages":      [],      # Display messages [{role, content, channel, intent, raw_json}]
        "agent_history": None,    # OpenAI Agents SDK input history (``result.to_input_list()``)
        "turn_count":    0,
        "last_intent":   None,
        "last_channel":  None,
        "system_ready":  False,
        "vector_store_ready": False,
        "orchestrator":  None,
        "init_error":    None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

init_session()


# ─── System Initialization (cached per VS ID, agents per session) ─────────────

@st.cache_resource(show_spinner=False)
def _get_vector_store_ids_cached():
    """
    Build or load OpenAI Vector Store ids once per app lifetime.
    Cached globally — not re-run on Streamlit reruns.
    """
    return VectorStoreService.default().ensure_sync()


def ensure_system_ready() -> bool:
    """
    Lazily initializes the agent system once per Streamlit session.
    Returns True if ready, False if initialization failed.
    """
    if st.session_state.system_ready:
        return True

    try:
        vector_store_ids = _get_vector_store_ids_cached()
        orchestrator = OpenAIAgentSystemFactory.default().build(vector_store_ids)
        st.session_state.vector_store_ready = True
        st.session_state.orchestrator = orchestrator
        st.session_state.system_ready = True
        st.session_state.init_error = None
        return True
    except Exception as e:
        st.session_state.init_error = str(e)
        st.session_state.system_ready = False
        return False


# ─── Agent Execution ──────────────────────────────────────────────────────────

async def _run_async(orchestrator, input_messages) -> object:
    """Async runner — OpenAI Agents SDK Runner."""
    return await Runner.run(orchestrator, input_messages)


def run_agent(orchestrator, user_message: str, agent_history) -> object:
    """
    Execute the OpenAI Agents SDK graph for one conversation turn.
    """
    session_id = st.session_state.session_id
    formatted = f"[SESSION_ID: {session_id}]\n\n{user_message}"
    input_messages = (
        agent_history + [{"role": "user", "content": formatted}]
        if agent_history
        else formatted
    )
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_run_async(orchestrator, input_messages))


def parse_response(result: object, session_id: str) -> ShowroomResponse:
    """Normalize OpenAI Agents ``RunResult`` into ``ShowroomResponse`` (never raises)."""
    return ShowroomAgentStateExtractor.default().from_run_result(result, session_id)


# ─── UI Components ────────────────────────────────────────────────────────────

def render_intent_badge(intent: str) -> str:
    meta = INTENT_META.get(intent, INTENT_META["unknown"])
    return (
        f'<span class="intent-badge badge-{meta["css"]}">'
        f'{meta["emoji"]} {meta["label"]}'
        f"</span>"
    )


def render_assistant_message(msg: dict) -> None:
    """
    Render a single assistant message with intent badge and JSON viewer.
    """
    channel = msg.get("channel", "text")
    intent  = msg.get("intent", "unknown")
    content = msg.get("content", "")

    channel_icon = CHANNEL_ICON.get(channel, "💬")
    st.markdown(f"{channel_icon} {content}")

    # Intent badge
    st.markdown(render_intent_badge(intent), unsafe_allow_html=True)

    # Channel-specific banners
    if channel == "voice":
        st.markdown(
            '<div class="banner-voice">🔊 Voice channel — text-to-speech (OpenAI Speech API)</div>',
            unsafe_allow_html=True,
        )
        st.caption(SYNTHETIC_SPEECH_DISCLOSURE)
        vp = msg.get("voice_playback") or {}
        b64 = vp.get("audio")
        if b64:
            try:
                st.audio(base64.b64decode(b64), format="audio/mpeg")
            except Exception:
                logger.exception("Streamlit audio decode or playback failed")
                st.warning("Could not play the generated audio in this browser session.")
        if vp.get("error"):
            st.warning(vp["error"])
    elif channel == "escalation":
        st.markdown(
            '<div class="banner-escalation">🔴 Human advisor notified — a specialist will contact you shortly</div>',
            unsafe_allow_html=True,
        )

    # Expandable JSON view
    if msg.get("raw_json"):
        with st.expander("View JSON response contract", expanded=False):
            st.code(json.dumps(msg["raw_json"], indent=2), language="json")


def render_welcome() -> None:
    """Render the welcome screen shown before any conversation."""
    st.markdown("""
    <div class="welcome-box">
        <div class="welcome-icon">⚡</div>
        <div class="welcome-title">Welcome to the Aether Motors Virtual Showroom</div>
        <div class="welcome-sub">
            Our AI assistant routes your questions to specialized agents for precise, grounded answers.
        </div>
        <div class="welcome-examples">
            <div style="margin-bottom:8px; color:#666676;">Try asking:</div>
            <span class="welcome-example">What's the 0-60 on the Aether GT Performance?</span>
            <span class="welcome-example">What layout fits a 300 sqm floor?</span>
            <span class="welcome-example">I want to reserve the GT Coupe in matte black</span>
            <span class="welcome-example">Do you offer lease options?</span>
            <span class="welcome-example">I'd like to speak with someone</span>
            <span class="welcome-example">Read that answer aloud for me</span>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_sidebar() -> None:
    """Render the sidebar with session info, agent pipeline, and controls."""
    with st.sidebar:
        st.markdown("## ⚡ SESSION")

        # Session ID
        st.markdown(f"""
        <div class="info-card">
            <div class="info-label">Session ID</div>
            <div class="info-value">{st.session_state.session_id}</div>
        </div>""", unsafe_allow_html=True)

        # Turn count
        st.markdown(f"""
        <div class="info-card">
            <div class="info-label">Conversation Turns</div>
            <div class="info-value">{st.session_state.turn_count}</div>
        </div>""", unsafe_allow_html=True)

        # Last intent
        if st.session_state.last_intent:
            meta = INTENT_META.get(st.session_state.last_intent, INTENT_META["unknown"])
            st.markdown(f"""
            <div class="info-card">
                <div class="info-label">Last Classified Intent</div>
                <div class="info-value">{meta["emoji"]} {meta["label"]}</div>
            </div>""", unsafe_allow_html=True)

        # System status
        status_color = "#4dcc80" if st.session_state.system_ready else "#ff6060"
        status_text  = "Online" if st.session_state.system_ready else "Offline"
        st.markdown(f"""
        <div class="info-card">
            <div class="info-label">System Status</div>
            <div class="info-value" style="color:{status_color};">● {status_text}</div>
        </div>""", unsafe_allow_html=True)

        st.markdown("---")

        st.markdown("### 🔊 Read aloud")
        st.caption(
            "There is no microphone input. Ask the assistant to **read a reply aloud**; when the "
            "response uses **channel: voice**, this app plays **AI-generated speech** (OpenAI TTS)."
        )

        st.markdown("---")

        # Agent pipeline display
        st.markdown("### 🤖 Agent Pipeline")
        for icon, name, desc in AGENTS_PIPELINE:
            is_active = (
                st.session_state.last_intent and
                any(intent in name.lower() for intent in
                    [st.session_state.last_intent.replace("_", "")])
            )
            css = "agent-node-active" if is_active else "agent-node"
            st.markdown(
                f'<div class="{css}">{icon} <strong>{name}</strong><br>'
                f'<span style="font-size:0.7rem;color:#555568;">{desc}</span></div>',
                unsafe_allow_html=True,
            )

        st.markdown("---")

        # Clear conversation
        if st.button("🗑️ Clear Conversation", use_container_width=True, type="secondary"):
            st.session_state.messages      = []
            st.session_state.agent_history = None
            st.session_state.turn_count    = 0
            st.session_state.last_intent   = None
            st.session_state.last_channel  = None
            st.session_state.session_id    = f"SES-{str(uuid.uuid4())[:8].upper()}"
            st.rerun()

        # Memory toggle info
        st.markdown(
            '<div style="font-size:0.7rem;color:#555568;margin-top:8px;">'
            '🧠 Conversation memory is active across all turns within this session.'
            '</div>',
            unsafe_allow_html=True,
        )


# ─── Main Application ─────────────────────────────────────────────────────────

def main() -> None:
    # Header
    st.markdown("""
    <div class="aether-header">
        <div class="aether-logo">⚡ Aether Motors</div>
        <div class="aether-tagline">AI Virtual Showroom · Multi-Agent Intelligence · RISEN Methodology</div>
    </div>
    """, unsafe_allow_html=True)

    # Sidebar
    render_sidebar()

    # System initialization
    if not st.session_state.system_ready:
        with st.spinner("⚡ Initializing AI Showroom System — loading knowledge base..."):
            ready = ensure_system_ready()

        if not ready:
            st.error(
                f"⚠️ System initialization failed.\n\n"
                f"**Error:** {st.session_state.init_error}\n\n"
                "Check that the `data/` folder is present and your OpenAI API key is valid."
            )
            return

    orchestrator = st.session_state.orchestrator

    # ── Display conversation history ──────────────────────────────────────────
    if not st.session_state.messages:
        render_welcome()
    else:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                if msg["role"] == "assistant":
                    render_assistant_message(msg)
                else:
                    st.markdown(msg["content"])

    # ── Chat input ────────────────────────────────────────────────────────────
    if prompt := st.chat_input("Ask about vehicles, layouts, purchasing, or anything else..."):

        # Immediately display user message
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Run agent and display response
        with st.chat_message("assistant"):
            with st.spinner("Routing to specialist agent..."):
                try:
                    result = run_agent(orchestrator, prompt, st.session_state.agent_history)

                    response = parse_response(result, st.session_state.session_id)

                    st.session_state.agent_history = result.to_input_list()
                    st.session_state.turn_count   += 1
                    st.session_state.last_intent   = response.intent
                    st.session_state.last_channel  = response.channel

                    wire = enrich_response_dict_with_tts(response.model_dump())
                    contract_json = showroom_response_contract_dict(wire)
                    voice_playback = wire.get("voice") if isinstance(wire.get("voice"), dict) else None
                    render_assistant_message({
                        "content":  response.message_agent,
                        "channel":  response.channel,
                        "intent":   response.intent,
                        "raw_json": contract_json,
                        "voice_playback": voice_playback,
                    })

                    # Persist to display history
                    st.session_state.messages.append({
                        "role":     "assistant",
                        "content":  response.message_agent,
                        "channel":  response.channel,
                        "intent":   response.intent,
                        "raw_json": contract_json,
                        "voice_playback": voice_playback,
                    })

                except Exception as exc:
                    error_msg = (
                        "I encountered an issue processing that request. "
                        "Please try again or rephrase your question."
                    )
                    st.error(f"Agent error: {exc}")
                    st.markdown(f"💬 {error_msg}")

                    # Save error turn to history (does not break session)
                    st.session_state.messages.append({
                        "role":    "assistant",
                        "content": error_msg,
                        "channel": "text",
                        "intent":  "error",
                    })


if __name__ == "__main__":
    main()
