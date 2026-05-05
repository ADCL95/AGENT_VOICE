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
import streamlit.components.v1 as components
import asyncio
import base64
import subprocess
import time
import uuid
import json
import nest_asyncio
import urllib.error
import urllib.request

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
_BRIDGE_URL = "http://127.0.0.1:8000"

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


def _is_bridge_healthy(base_url: str = _BRIDGE_URL) -> bool:
    """Return True when FastAPI bridge responds to /health."""
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=1.0) as resp:  # noqa: S310
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


@st.cache_resource(show_spinner=False)
def ensure_bridge_running() -> subprocess.Popen[str] | None:
    """
    Ensure FastAPI bridge is running for voice realtime.

    If an external bridge already runs on :8000, this function is a no-op.
    Otherwise, it starts ``python server.py`` once per Streamlit process.
    """
    if _is_bridge_healthy():
        return None

    command = [sys.executable, str(_REPO_ROOT / "server.py")]
    kwargs: dict[str, object] = {
        "cwd": str(_REPO_ROOT),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "text": True,
    }
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(command, **kwargs)  # noqa: S603
    for _ in range(30):
        if _is_bridge_healthy():
            return proc
        time.sleep(0.2)

    # Startup failed: stop child process to avoid orphan workers.
    try:
        proc.terminate()
    except Exception:
        logger.exception("Failed to terminate auto-started server.py process")
    raise RuntimeError(
        "Could not start the FastAPI bridge on http://127.0.0.1:8000. "
        "Check your local configuration and port availability."
    )


def render_realtime_voice_control() -> None:
    """
    Render a compact ChatGPT-like voice control (single click to talk) directly in Streamlit.
    """
    voice_session_id = st.session_state.session_id
    components.html(
        f"""
        <div id="rt-voice-root" style="display:flex;align-items:center;gap:10px;padding:8px 0 2px 0;min-height:56px;">
          <button id="rt-voice-btn"
                  style="width:44px;height:44px;border-radius:50%;border:1px solid rgba(176,106,255,0.35);
                         background:rgba(176,106,255,0.16);color:#d7b6ff;font-size:18px;cursor:pointer;">
            🎙️
          </button>
          <div style="display:flex;flex-direction:column;gap:3px;">
            <span id="rt-voice-label" style="font-size:12px;color:#a8a8c0;letter-spacing:.06em;text-transform:uppercase;">
              Realtime Voice Ready
            </span>
            <span id="rt-voice-sub" style="font-size:11px;color:#6e6e86;">
              Click once and start speaking
            </span>
          </div>
        </div>
        <div style="display:flex;gap:8px;align-items:center;margin:2px 0 6px 2px;">
          <span id="fc-on-badge" style="font-size:10px;padding:2px 8px;border-radius:999px;border:1px solid #35634a;background:rgba(60,140,90,.18);color:#7be0a1;">
            Function call: ON
          </span>
          <span id="fc-last-badge" style="font-size:10px;padding:2px 8px;border-radius:999px;border:1px solid #3a3a52;background:rgba(80,80,120,.18);color:#b8b8d8;">
            Last call: idle
          </span>
        </div>

        <script>
        const SERVER_URL = "{_BRIDGE_URL}";
        const btn = document.getElementById("rt-voice-btn");
        const label = document.getElementById("rt-voice-label");
        const sub = document.getElementById("rt-voice-sub");
        const fcLastBadge = document.getElementById("fc-last-badge");

        let ws = null;
        let audioCtx = null;
        let micStream = null;
        let micNode = null;
        let playbackCtx = null;
        let nextPlayTime = 0;
        let usingLocalVerbatimTts = false;
        let activePlaybackSources = [];

        function setLastCallState(state) {{
          // state: idle | running | ok | error
          if (!fcLastBadge) return;
          if (state === "running") {{
            fcLastBadge.textContent = "Last call: running";
            fcLastBadge.style.borderColor = "#8a6f2e";
            fcLastBadge.style.background = "rgba(255,200,60,.18)";
            fcLastBadge.style.color = "#ffd27a";
            return;
          }}
          if (state === "ok") {{
            fcLastBadge.textContent = "Last call: ok";
            fcLastBadge.style.borderColor = "#35634a";
            fcLastBadge.style.background = "rgba(60,140,90,.18)";
            fcLastBadge.style.color = "#7be0a1";
            return;
          }}
          if (state === "error") {{
            fcLastBadge.textContent = "Last call: error";
            fcLastBadge.style.borderColor = "#7a3030";
            fcLastBadge.style.background = "rgba(180,70,70,.18)";
            fcLastBadge.style.color = "#ff9c9c";
            return;
          }}
          fcLastBadge.textContent = "Last call: idle";
          fcLastBadge.style.borderColor = "#3a3a52";
          fcLastBadge.style.background = "rgba(80,80,120,.18)";
          fcLastBadge.style.color = "#b8b8d8";
        }}

        function setUi(state) {{
          if (state === "connecting") {{
            label.textContent = "Connecting...";
            sub.textContent = "Requesting token and microphone";
            btn.style.background = "rgba(255,192,64,.2)";
            return;
          }}
          if (state === "listening") {{
            label.textContent = "Listening";
            sub.textContent = "Speak naturally (server VAD enabled)";
            btn.style.background = "rgba(77,204,128,.22)";
            return;
          }}
          if (state === "speaking") {{
            label.textContent = "Assistant Speaking";
            sub.textContent = "AI voice response in progress";
            btn.style.background = "rgba(255,215,0,.2)";
            return;
          }}
          if (state === "error") {{
            label.textContent = "Voice Error";
            sub.textContent = "Check mic permission / backend health";
            btn.style.background = "rgba(255,96,96,.2)";
            return;
          }}
          label.textContent = "Realtime Voice Ready";
          sub.textContent = "Click once and start speaking";
          btn.style.background = "rgba(176,106,255,.16)";
        }}

        function floatToPcm16(floatArray) {{
          const pcm = new Int16Array(floatArray.length);
          for (let i = 0; i < floatArray.length; i++) {{
            const s = Math.max(-1, Math.min(1, floatArray[i]));
            pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
          }}
          return pcm;
        }}

        function toBase64(buffer) {{
          const bytes = new Uint8Array(buffer);
          let binary = "";
          for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
          return btoa(binary);
        }}

        function fromBase64ToInt16(b64) {{
          const raw = atob(b64);
          const out = new Int16Array(raw.length / 2);
          for (let i = 0; i < out.length; i++) {{
            out[i] = (raw.charCodeAt(i * 2 + 1) << 8) | raw.charCodeAt(i * 2);
          }}
          return out;
        }}

        function playChunk(int16Data) {{
          if (!playbackCtx) {{
            playbackCtx = new (globalThis.AudioContext || globalThis.webkitAudioContext)({{ sampleRate: 24000 }});
          }}
          const f32 = new Float32Array(int16Data.length);
          for (let i = 0; i < int16Data.length; i++) f32[i] = int16Data[i] / 32768;
          const buff = playbackCtx.createBuffer(1, f32.length, 24000);
          buff.getChannelData(0).set(f32);
          const src = playbackCtx.createBufferSource();
          src.buffer = buff;
          src.connect(playbackCtx.destination);
          activePlaybackSources.push(src);
          src.onended = () => {{
            activePlaybackSources = activePlaybackSources.filter((s) => s !== src);
          }};
          const now = playbackCtx.currentTime;
          if (nextPlayTime < now) nextPlayTime = now;
          src.start(nextPlayTime);
          nextPlayTime += buff.duration;
        }}

        function stopAssistantPlayback() {{
          try {{
            for (const src of activePlaybackSources) {{
              try {{ src.stop(); }} catch {{}}
              try {{ src.disconnect(); }} catch {{}}
            }}
          }} finally {{
            activePlaybackSources = [];
            nextPlayTime = 0;
          }}
        }}


        async function startMic() {{
          micStream = await navigator.mediaDevices.getUserMedia({{
            audio: {{ sampleRate: 24000, channelCount: 1, echoCancellation: true, noiseSuppression: true }}
          }});
          audioCtx = new (globalThis.AudioContext || globalThis.webkitAudioContext)({{ sampleRate: 24000 }});
          const src = audioCtx.createMediaStreamSource(micStream);
          micNode = audioCtx.createScriptProcessor(2048, 1, 1);
          src.connect(micNode);
          micNode.connect(audioCtx.destination);
          micNode.onaudioprocess = (e) => {{
            if (!ws || ws.readyState !== WebSocket.OPEN) return;
            const pcm16 = floatToPcm16(e.inputBuffer.getChannelData(0));
            ws.send(JSON.stringify({{ type: "input_audio_buffer.append", audio: toBase64(pcm16.buffer) }}));
          }};
        }}

        function stopMic() {{
          if (micNode) {{ micNode.disconnect(); micNode = null; }}
          if (audioCtx) {{ audioCtx.close().catch(() => {{}}); audioCtx = null; }}
          if (micStream) {{ micStream.getTracks().forEach((t) => t.stop()); micStream = null; }}
        }}

        async function connectVoice() {{
          setUi("connecting");
          let token = "";
          let model = "gpt-4o-mini-realtime-preview";
          try {{
            const r = await fetch(`${{SERVER_URL}}/voice-token`);
            if (!r.ok) throw new Error("voice-token HTTP " + r.status);
            const data = await r.json();
            token = data.token;
            model = data.model || model;
          }} catch {{
            setUi("error");
            return;
          }}

          try {{
            ws = new WebSocket(`wss://api.openai.com/v1/realtime?model=${{encodeURIComponent(model)}}`, [
              "realtime",
              `openai-insecure-api-key.${{token}}`,
              "openai-beta.realtime-v1",
            ]);
          }} catch {{
            setUi("error");
            return;
          }}

          ws.onopen = async () => {{
            ws.send(JSON.stringify({{
              type: "session.update",
              session: {{
                modalities: ["text", "audio"],
                instructions: "For every user question, call query_showroom_agents first. Then answer using ONLY the tool output. Do not add external facts. Be concrete and concise. Keep names, layout IDs, numbers, capacities, and measurements exactly as provided by the tool.",
                voice: "alloy",
                input_audio_format: "pcm16",
                output_audio_format: "pcm16",
                input_audio_transcription: {{ model: "whisper-1" }},
                turn_detection: {{ type: "server_vad", threshold: 0.5, prefix_padding_ms: 300, silence_duration_ms: 350 }},
                max_output_tokens: 320,
                tools: [{{
                  type: "function",
                  name: "query_showroom_agents",
                  description: "Use to query the Aether Motors multi-agent RAG system.",
                  parameters: {{
                    type: "object",
                    properties: {{ query: {{ type: "string" }} }},
                    required: ["query"]
                  }}
                }}],
                tool_choice: "required",
                temperature: 0.1,
              }}
            }}));
            try {{
              await startMic();
              setUi("listening");
            }} catch {{
              setUi("error");
            }}
          }};

          ws.onmessage = async (ev) => {{
            let msg = null;
            try {{ msg = JSON.parse(ev.data); }} catch {{ return; }}
            if (msg.type === "response.audio.delta" && msg.delta) {{
              if (usingLocalVerbatimTts) {{
                return;
              }}
              try {{
                playChunk(fromBase64ToInt16(msg.delta));
                setUi("speaking");
              }} catch {{}}
              return;
            }}
            if (msg.type === "response.done") {{
              nextPlayTime = 0;
              setUi("listening");
              return;
            }}
            if (msg.type === "input_audio_buffer.speech_started") {{
              // If user starts speaking while assistant audio is playing, cut playback immediately.
              stopAssistantPlayback();
              setUi("listening");
              return;
            }}
            if (msg.type === "response.function_call_arguments.done" && msg.name === "query_showroom_agents") {{
              setLastCallState("running");
              let query = "";
              try {{ query = JSON.parse(msg.arguments || "{{}}").query || ""; }} catch {{}}
              const quickQuery = query.trim().toLowerCase();
              if (!quickQuery) {{
                if (ws && ws.readyState === WebSocket.OPEN) {{
                  ws.send(JSON.stringify({{
                    type: "conversation.item.create",
                    item: {{
                      type: "function_call_output",
                      call_id: msg.call_id,
                      output: "Please ask your question again. I will route it through the showroom agent orchestrator.",
                    }}
                  }}));
                  ws.send(JSON.stringify({{
                    type: "response.create",
                    response: {{
                      instructions: "Respond in one short sentence.",
                      max_output_tokens: 120,
                    }}
                  }}));
                }}
                return;
              }}

              let output = "I could not retrieve that information right now.";
              try {{
                const rsp = await fetch(`${{SERVER_URL}}/agent`, {{
                  method: "POST",
                  headers: {{ "Content-Type": "application/json" }},
                  body: JSON.stringify({{ query, session_id: "{voice_session_id}" }}),
                }});
                if (rsp.ok) {{
                  const data = await rsp.json();
                  output = data.message_agent || output;
                  setLastCallState("ok");
                }} else {{
                  setLastCallState("error");
                }}
              }} catch {{
                setLastCallState("error");
              }}
              if (ws && ws.readyState === WebSocket.OPEN) {{
                const verbatimPayload =
                  "VERBATIM_START\\n" + output + "\\nVERBATIM_END";
                ws.send(JSON.stringify({{
                  type: "conversation.item.create",
                  item: {{
                    type: "function_call_output",
                    call_id: msg.call_id,
                    output: verbatimPayload
                  }}
                }}));

                ws.send(JSON.stringify({{
                  type: "response.create",
                  response: {{
                    instructions: "Read ONLY the text between VERBATIM_START and VERBATIM_END from the latest tool output. Do not summarize, rephrase, reorder, add, or remove details. Preserve layout IDs, names, numbers, capacities, prices, and measurements exactly as written. If escalation details exist, read all escalation details exactly.",
                    output_modalities: ["audio"],
                    max_output_tokens: 512,
                    temperature: 0,
                  }}
                }}));
              }}
            }}
          }};

          ws.onerror = () => setUi("error");
          ws.onclose = () => {{
            stopMic();
            ws = null;
            nextPlayTime = 0;
            setUi("idle");
          }};
        }}

        function disconnectVoice() {{
          stopAssistantPlayback();
          stopMic();
          if (ws) {{
            ws.close(1000, "user_stop");
            ws = null;
          }}
          setUi("idle");
        }}

        btn.addEventListener("click", async () => {{
          if (ws && ws.readyState === WebSocket.OPEN) {{
            disconnectVoice();
            return;
          }}
          await connectVoice();
        }});

        globalThis.addEventListener("beforeunload", disconnectVoice);
        </script>
        """,
        height=130,
    )


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

        st.markdown("### 🎙️ Realtime Voice Chat")
        st.caption(
            "Click the microphone to start/stop real-time conversation. "
            "No extra panel or extra script needed."
        )
        render_realtime_voice_control()

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
    try:
        ensure_bridge_running()
    except Exception as exc:
        st.error(
            "⚠️ Automatic backend startup failed. "
            "The app could not launch `server.py` on port 8000."
        )
        st.caption(f"Details: {exc}")
        return

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
