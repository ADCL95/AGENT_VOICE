<!--
Sync Impact Report
- Version change: 1.2.0 → 1.2.1 (PATCH: single local.settings.json; optional keys documented in README; removed local.settings.example.json from governance text.)
- Prior: 1.1.0 → 1.2.0 (MINOR: explicit binding to AI Engineer Technical Challenge; dual architecture artifacts; stack deviation and Realtime obligations; README and evaluator alignment.)
- Principles: I expanded (dual SoT + challenge); II tightened (channel semantics for embedder); III expanded (corpus map + minimum two intents + optional third); IV unchanged intent; V expanded (README MUST, single-agent failure MUST NOT take down system, voice degradation).
- Added: "Challenge alignment (technical trial)" subsection under Additional constraints; explicit Realtime vs documented deviation rule.
- Removed sections: none.
- Templates: .specify/templates/plan-template.md ✅; spec-template.md ✅; tasks-template.md ✅ (no template edits required).
- Follow-up: if Realtime lifecycle is extended beyond documented deviation, update architecture Section 12 and bump this file PATCH with date.
-->

# Virtual Showroom Multi-Agent Assistant Constitution

## Core Principles

### I. Architecture documents and the technical challenge as source of truth

This repository implements the **AI Engineer Technical Challenge — Multi-Agent AI System for an Immersive Digital Showroom**. That brief is **binding** for scope, intents, JSON contract, stack expectations, and evaluator-facing deliverables.

**Authoritative design (full narrative, diagrams, Spanish context where applicable):** `documents/ARQUITECTURA_SHOWROOM_VIRTUAL.md`.

**Challenge-aligned English summary for evaluators and engineers (condensed mapping, assumptions, tradeoffs):** `documents/TECHNICAL_ARCHITECTURE_SUMMARY.md`. This summary MUST remain **consistent** with the full architecture document whenever either is updated.

Day-to-day editor invariants live in `.cursor/rules/showroom-core.mdc`. Any **material** behavior or integration change MUST update the architecture document first; the technical summary MUST be revised in the same change when it describes that behavior. **Stack deviations** from the brief’s defined stack (tools, voice path, etc.) MUST appear in the architecture document under **Stack Deviations** with (1) what changed, (2) why, (3) tradeoffs — deviations without this disclosure are treated as **unmet** requirements for evaluation purposes.

### II. Multi-agent orchestration and fixed client contract (NON-NEGOTIABLE)

The system MUST remain **multi-agent**: distinct agents with separated responsibilities, orchestration via **OpenAI Agents SDK** (`openai-agents`) using an explicit graph (orchestrator + specialists + **handoffs**), not a single undifferentiated prompt that replaces routing.

**Minimum intents** (with semantics aligned to the brief): **Product Info**, **Space Analysis**, **Purchase Intent**, **Voice Request**, **Escalation**. Additional intents MUST be justified in `documents/ARQUITECTURA_SHOWROOM_VIRTUAL.md`.

Every client-visible turn MUST serialize to **exactly** these four root fields: `message_agent`, `channel`, `intent`, `session_id`. The `channel` value MUST be exactly one of `text`, `voice`, or `escalation` so an embeddable 3D host can branch **without** parsing free-form model text. `channel` MUST be set by **deterministic policy** (orchestrator rules, specialist structured output, HTTP layer). The architecture document MAY define **graceful degradation** (e.g. voice → text on TTS or Realtime failure); degradation MUST NOT remove or invalidate the four-field contract at the root.

### III. RAG grounded in the three challenge corpora

RAG MUST be anchored to the three plain-text knowledge bases under `data/`: `vehicle_catalog.txt`, `dealership_faq.txt`, `showroom_layouts.txt`. **At least two** intents MUST demonstrably retrieve from these files; the implemented design MUST keep **Product Info** and **Space Analysis** as retrieval-backed, and SHOULD keep **Purchase Intent** grounded in `dealership_faq.txt` where applicable, per the architecture summary.

The prescribed production mechanism is **OpenAI Vector Store + FileSearchTool** (hosted file search), with **scoped** tools or stores per specialist so retrieval stays auditable. Synthetic corpus additions MUST be **clearly labeled** in file or metadata as non-original if introduced.

### IV. Secrets, configuration, and English-only technical surface

Secrets and endpoints MUST load from `local.settings.json` (gitignored) via `src/core/`. Optional keys and setup instructions MUST live in `README.md` (no second settings file in the repo). No API keys, tokens, or customer PII MUST be committed to the repository.

All **new** technical artifacts (code, symbols, comments, docstrings, developer logs, tests, and new technical Markdown) MUST be written in **English**. Pre-existing or submission-required documents in other languages are the only exception.

### V. Reliability, observability, async-first delivery, and evaluator runnability

The critical path MUST be **async-first** (`asyncio`); any synchronous choice on the hot path MUST be justified in the architecture document.

At every boundary (agent invocation, RAG tools, external adapters, HTTP/WebSocket), Python code MUST use explicit `try` / `except`. **One failing agent or tool MUST NOT take down the whole system** — log, degrade, and return a controlled JSON response where the architecture defines that behavior. Exceptions MUST NOT be swallowed: log with **full traceback** (`logging.exception` or `logger.error(..., exc_info=True)`) and structured fields including at minimum `session_id` and a component step (e.g. `classify`, `retrieve`, `generate`, `assemble`, `realtime`).

The stack MUST target **Python 3.11+**. The root **README.md** MUST remain sufficient for an evaluator to **run the project locally without asking questions** whenever setup, ports, or prerequisites change.

**Voice / Realtime (brief):** the challenge requires the **OpenAI Realtime API** (`wss://api.openai.com/v1/realtime`) for the voice channel and a Realtime session lifecycle (setup, user audio, agent audio, teardown) at minimum. If the default demo path uses a **documented** alternative (e.g. Speech API TTS with optional token endpoint for Realtime exploration), that alternative MUST remain fully explained under **Stack Deviations** with tradeoffs, and any partial Realtime path MUST remain **demonstrable** or **documented** per the architecture doc — silent mismatch with the written brief is unacceptable.

## Additional constraints (stack, layout, and challenge alignment)

- Backend layout under `src/showroom/` MUST follow the established modules: `core`, `domain`, `agents` (graph, prompts, tools, factory), `rag`, `infrastructure`, `presentation`.
- Front-end demos under `front-end/` MUST consume the same **four-field** JSON contract at the HTTP boundary unless a **documented** demo-only exception exists in the architecture doc.
- **Multi-turn** conversation state MUST be honored where the product claims it (e.g. Streamlit demo with `agent_history` / `to_input_list()`); `session_id` MUST always be echoed in the contract and used in logs. Stateless HTTP bridges MUST document how `session_id` correlates and what a production session store would add (per architecture summary).
- **Challenge alignment (technical trial):** features, refactors, and specs MUST NOT contradict the multi-agent + RAG + structured JSON + session + voice/escalation semantics of the **AI Engineer Technical Challenge** unless the architecture **Stack Deviations** section already covers the same ground.

## SDD workflow in this repository

This repository uses **GitHub Spec Kit** (Specify CLI + Cursor skills under `.cursor/skills/speckit-*`). Feature work SHOULD follow the kit order when practical: **constitution** (this file) → **specify** (`/speckit-specify`) → optional **clarify** → **plan** (`/speckit-plan`) → optional **checklist** → **tasks** (`/speckit-tasks`) → optional **analyze** → **implement** (`/speckit-implement`). Feature artifacts SHOULD live under `specs/<branch-or-feature>/` as produced by the bundled scripts.

Plans MUST include a **Constitution Check** gate; violations MUST be justified in the plan or resolved by updating specs or this constitution.

## Governance

- This constitution **supersedes** ad-hoc agent instructions when they conflict on governance topics (challenge scope, contract, intents, RAG scope, secrets, language, stack deviations).
- **Amendments:** Any change that adds, removes, or redefines a principle requires updating this file, bumping `CONSTITUTION_VERSION`, setting `LAST_AMENDED_DATE` to the change date, and aligning `documents/ARQUITECTURA_SHOWROOM_VIRTUAL.md`, `documents/TECHNICAL_ARCHITECTURE_SUMMARY.md`, and `.cursor/rules/showroom-core.mdc` when editor or runtime invariants change.
- **Versioning:** **MAJOR** — removal or incompatible redefinition of a principle. **MINOR** — new principle or section, or materially expanded obligation. **PATCH** — clarifications and non-semantic wording.
- **Compliance:** Substantial changes touching routing, RAG, the four-field contract, voice, Realtime, or escalation MUST explicitly confirm alignment with this constitution, the technical summary, and the full architecture document.

**Version**: 1.2.1 | **Ratified**: 2026-04-16 | **Last Amended**: 2026-04-16
