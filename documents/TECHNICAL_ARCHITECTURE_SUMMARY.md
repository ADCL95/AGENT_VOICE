# Virtual Showroom Assistant — Technical Architecture Summary

**Audience:** evaluators and engineers running the challenge locally  


This document maps the **AI Engineer Technical Challenge** requirements to the implemented system, states **assumptions**, and highlights **technical tradeoffs**. 

---

## 1. Business context and problem (brief alignment)

- **Product:** B2B SaaS for high-value sales inside a **3D virtual showroom**.
- **Problem:** Buyers ask heterogeneous questions (specs, space fit, purchase path, voice read-back, human handoff). The assistant must **route** each turn correctly and return **channel-aware** output for the embedding host.
- **Key constraint:** Every client-visible turn must serialize to a **fixed JSON contract** so the 3D host can branch on `channel` without parsing free-form model text.

---

## 2. Challenge requirements — how they are met


| Requirement                                      | Implementation summary                                                                                                                                                                                                                                                                          |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Multi-agent** with clear separation            | **OpenAI Agents SDK** graph: `OrchestratorAgent` + four specialists (`ProductInfoAgent`, `SpaceAnalysisAgent`, `PurchaseIntentAgent`, `EscalationAgent`) wired via **handoffs** (`ShowroomOpenAIAgentGraphBuilder`, `multi_agent_system.py`).                                                   |
| **Intent classification** (minimum five intents) | Routing is **orchestrator prompt + handoffs**, not a separate classifier agent. All five brief intents are supported: Product Info, Space Analysis, Purchase Intent, Voice Request, Escalation (Voice Request routes to a specialist, typically product, with `channel: voice` for read-aloud). |
| **RAG** over three `.txt` files                  | **OpenAI Vector Store + `FileSearchTool`** per corpus (`vehicle_catalog.txt`, `showroom_layouts.txt`, `dealership_faq.txt`). **At least two intents** use retrieval demonstrably: **Product Info** and **Space Analysis**; **Purchase Intent** uses FAQ retrieval.                              |
| **Structured JSON every turn**                   | `ShowroomResponse` (Pydantic) as `output_type` on specialists; four root fields: `message_agent`, `channel`, `intent`, `session_id`.                                                                                                                                                            |
| **Multi-turn state**                             | **Streamlit** (`front-end/app.py`): `agent_history` + `result.to_input_list()` for full OpenAI Agents-compatible history. `**POST /agent` + `voice.html`**: stateless on server (single-turn unless user packs context in `query`); `session_id` is for correlation and contract echo.          |
| **Voice / Realtime**                             | Implemented with **OpenAI Realtime WSS** in `front-end/app.py` (sidebar mic button). The flow uses `session.update` with a function tool (`query_showroom_agents`), `tool_choice: required`, handles `response.function_call_arguments.done`, executes `POST /agent`, sends `function_call_output`, then triggers `response.create`. |
| **Async-first**                                  | FastAPI path and agent `Runner.run` are async; TTS enrichment may use `asyncio.to_thread` to avoid blocking the event loop.                                                                                                                                                                     |
| **Error handling**                               | Boundaries log with traceback (`logging.exception` / `exc_info=True`), structured context (`session_id`, step). TTS failures attach `voice.error` without breaking the four-field contract.                                                                                                     |
| **Local README**                                 | Reproducible run instructions in repository `README.md`; secrets and optional model keys in `local.settings.json` (gitignored), documented in README.                                                                                                                                           |


---

## 3. Agent decomposition (why these boundaries)


| Agent                   | Responsibility                                                                                                                                            | RAG corpus             |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| **OrchestratorAgent**   | Single entry: interpret user turn (including `[SESSION_ID: …]` prefix), enforce intent priority, perform **exactly one handoff** to the right specialist. | None                   |
| **ProductInfoAgent**    | Vehicle specs, trims, performance; may set `channel: voice` **for read-aloud tied to product answers.**                                                   | `vehicle_catalog.txt`  |
| **SpaceAnalysisAgent**  | Layout recommendations by floor area / tier.                                                                                                              | `showroom_layouts.txt` |
| **PurchaseIntentAgent** | Reservation / next commercial steps; dealership process questions.                                                                                        | `dealership_faq.txt`   |
| **EscalationAgent**     | Empathetic copy + `**channel: escalation`** for human handoff.                                                                                            | None                   |


**Design rationale:** separating **orchestration** from **domain specialists** keeps prompts testable, confines **FileSearch** to the smallest necessary vector store per agent, and isolates **escalation** from generative sales language.

**Assumption:** a dedicated “Voice Request” sub-agent is unnecessary if specialists can emit `channel: voice` when the user asks to hear content again; the orchestrator prompt encodes default routing for ambiguous “read that back” requests.

---

## 4. End-to-end workflow (conceptual)

1. **Input:** user text + `session_id` (Streamlit also passes accumulated `agent_history` into `Runner.run`).
2. **Formatting:** user message may include `[SESSION_ID: …]` so the model echoes `session_id` in `ShowroomResponse`.
3. **Run:** `Runner.run(orchestrator, input_messages)`.
4. **Handoff:** orchestrator delegates to one specialist; specialist runs **hosted file search** then structured output.
5. **Extract:** `ShowroomAgentStateExtractor` maps run result to `ShowroomResponse`.
6. **Voice round-trip (Realtime):** browser sends microphone audio over WSS, model triggers `query_showroom_agents`, frontend calls `POST /agent`, and returns `function_call_output` to Realtime before audio reply synthesis.
7. **Barge-in:** when the user speaks while assistant audio is playing, client handles `input_audio_buffer.speech_started` and interrupts playback immediately.

**Branching:** escalation and voice are **not** free-text channel decisions — they follow orchestration rules and specialist output schema; HTTP layer may apply deterministic policy (e.g. TTS availability).

---

## 5. RAG strategy (chunking, indexing, operations)

- **Stack:** OpenAI **Files API** → **Vector Store** → attach `data/*.txt` → wait until store attachments reach `**completed`** before treating retrieval as ready.
- **Runtime:** Agents SDK `**FileSearchTool`** (Responses API `file_search`) against the provisioned `vector_store_id`(s), bound per agent via `ShowroomVectorStoreToolSet` (`agents/tools/rag_search.py`).
- **Chunking (design intent):** preserve logical blocks per file type; attach metadata such as `source_file`, vehicle/trim identifiers, FAQ `topic`, layout `sqm_range` / `tier` for traceability and optional filtering.
- **Why hosted file search:** aligns with the challenge’s prescribed production stack, minimizes custom embedding pipelines, and keeps retrieval upgrades on the provider side.

---

## 6. Response contract (critical for UI)

Every turn exposed to the client conforms to:

```json
{
  "message_agent": "string",
  "channel": "text | voice | escalation",
  "intent": "string",
  "session_id": "string"
}
```

**Channel semantics (brief):**

- `text` → chat overlay.
- `voice` → host uses **Realtime voice session** with function-calling to the same orchestrator pipeline.
- `escalation` → human handoff signal.

**Technical note:** malformed or missing `channel` can **silently break** embedders; the system prefers **schema-validated** specialist output rather than raw model JSON.

---

## 7. Stack notes (voice implementation)

Summary of the currently implemented voice stack:


| Topic                      | Current implementation                                                                                                                                                                                                                   |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Voice channel runtime**  | Streamlit sidebar button opens a Realtime microphone session (WSS) and uses server-side VAD.                                                                                                                                          |
| **Function-calling policy**| `query_showroom_agents` is always available with `tool_choice: required`; each tool call is executed through `POST /agent` so voice uses the same orchestrator + specialist + RAG path as text.                                      |
| **Fidelity controls**      | Realtime response instructions enforce reading tool output verbatim (preserving IDs and numeric facts).                                                                                                                                |
| **Latency controls**       | Lower VAD silence threshold, reduced audio buffer size, and short TTL cache for repeated factual queries in `ShowroomAgentPipelineFacade`.                                                                                            |


Orchestration (**OpenAI Agents SDK**) and RAG (**Vector Store + FileSearchTool**) follow the defined stack.

---

## 8. State management — assumptions

- **Demo truth for multi-turn memory:** Streamlit session state + OpenAI Agents history list.
- **HTTP API:** intentionally **stateless** regarding chat history to keep the bridge simple; production would add a **session repository** (e.g. Redis) and reconstruct `input_messages` like Streamlit does.
- `**session_id`:** always returned for correlation; in the stateless HTTP path it does not alone restore prior turns unless backend storage is added.

---

## 9. Non-goals (explicit)

- No requirement for cloud deployment, full 3D engine integration, or perfect RAG recall.
- No AWS-specific infrastructure in scope for the challenge.

---

## 10. What we would improve with more time

- RAG **golden-set** regression tests per intent and corpus.
- **Cross-encoder reranking** and faithfulness metrics in CI.
- Explicit **multilingual** classification and response policy.
- Human review **queue UI** for escalations.
- Latency **SLOs** (p95) split by retrieve vs generate vs TTS.

---

## 11. Code map (quick reference)

- **Orchestration:** `src/showroom/agents/graph/multi_agent_system.py`, `factory.py`, `prompts/*.py`
- **Contract:** `src/showroom/domain/schemas.py`
- **RAG lifecycle:** `src/showroom/rag/infrastructure/openai/`, `application/services/vector_store_service.py`
- **HTTP bridge:** `src/showroom/presentation/server.py` (root `server.py` launches uvicorn)
- **Primary UI:** `front-end/app.py`; minimal HTTP client: `front-end/voice.html`

