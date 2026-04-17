# Aether Motors — AI Virtual Showroom

Multi-agent conversational assistant with RAG (**OpenAI Vector Store + FileSearchTool**), Streamlit UI, and a voice client (OpenAI Realtime API) bridged through FastAPI.

## Prerequisites

- Python **3.11+**
- OpenAI API key with access to the models you set in `local.settings.json` (see Configuration)

## How it works (data flow)

1. **Streamlit** ([`front-end/app.py`](front-end/app.py)) is the main chat UI. It invokes the OpenAI **Agents SDK** (`Runner.run`) with an orchestrator built by [`OpenAIAgentSystemFactory`](src/showroom/agents/factory.py). The orchestrator hands off to five specialists (product, space, purchase, voice, escalation).
2. **RAG / OpenAI Vector Store** — [`VectorStoreService`](src/showroom/rag/application/services/vector_store_service.py) ensures an OpenAI Vector Store exists and uploads `data/*.txt` through [`OpenAIVectorIndexLifecycle`](src/showroom/rag/infrastructure/openai/lifecycle.py), waiting until each attached file reports API status `completed` (OpenAI file search / retrieval lifecycle). Specialists retrieve context with hosted [`FileSearchTool`](src/showroom/agents/tools/rag_search.py) (Responses API `file_search`).
3. **Voice (browser)** ([`front-end/voice.html`](front-end/voice.html)) connects to OpenAI Realtime over WebSocket for audio. When the model needs showroom knowledge, it calls your **FastAPI** bridge ([`showroom.presentation.server`](src/showroom/presentation/server.py)) `POST /agent`, which runs the same multi-agent pipeline and returns JSON matching [`ShowroomResponse`](src/showroom/domain/schemas.py).
4. **Configuration** ([`AppSettings` / `get_settings()`](src/showroom/core/settings.py)) loads secrets from `local.settings.json` or environment variables — never from committed source.
5. **HTTP bridge** ([`ShowroomHttpApplication`](src/showroom/presentation/server.py)) composes FastAPI; **Facade** `ShowroomAgentPipelineFacade` wraps agent execution. The Agents SDK uses `set_default_openai_key` for the model runtime; **Singleton** `OpenAIProvider` supplies a synchronous `OpenAI` client for vector-store provisioning under `showroom.rag`.

Python layout follows [`documents/ARQUITECTURA_SHOWROOM_VIRTUAL.md`](documents/ARQUITECTURA_SHOWROOM_VIRTUAL.md): code lives under `src/showroom/` (subfolders `core`, `helpers`, `domain`, `agents`, `rag`, `infrastructure`, `presentation`). The orchestration layer is the OpenAI **`agents`** SDK.

### Vector index (where it lives)

Knowledge files live in OpenAI **Vector Stores** in the account configured by `OPENAI_API_KEY`. At runtime, the app resolves store ids in this order: **(1)** non-empty environment variables **`VECTOR_STORE_ID_VEHICLE_CATALOG`**, **`VECTOR_STORE_ID_DEALERSHIP_FAQ`**, **`VECTOR_STORE_ID_SHOWROOM_LAYOUTS`** (highest priority); **(2)** the manifest file **`.vector_store_id`** (JSON map filename → `vs_…`, written after provisioning); **(3)** create stores and upload `data/*.txt` if neither is valid.

You can set the three `VECTOR_STORE_ID_*` variables in the shell (see below) or add the same keys to **`local.settings.json`** — on import, empty env vars are filled from JSON so RAG picks them up without `setx`.

Generate or refresh ids and print PowerShell exports:

```bash
python scripts/export_vector_store_env.py
```

Persist them for future terminals (Windows user env):

```bash
python scripts/export_vector_store_env.py --persist-user-env
```

**PowerShell (current session),** e.g. when reusing one store for all corpora:

```powershell
$env:VECTOR_STORE_ID_VEHICLE_CATALOG = "vs_xxxxxxxx"
$env:VECTOR_STORE_ID_DEALERSHIP_FAQ = "vs_xxxxxxxx"
$env:VECTOR_STORE_ID_SHOWROOM_LAYOUTS = "vs_xxxxxxxx"
```

## Terminal: auto-activate venv (Cursor / VS Code)

The workspace [`.vscode/settings.json`](.vscode/settings.json) sets:

- `python.defaultInterpreterPath` → `venv/Scripts/python.exe`
- `python.terminal.activateEnvironment` → `true`

Open a **new** integrated terminal after selecting the interpreter; the virtual environment should activate automatically.

## Configuration

Create **`local.settings.json`** in the **repository root** (this file is gitignored). Minimal shape:

```json
{
  "OPENAI_API_KEY": "sk-..."
}
```

Optional keys (defaults match `src/showroom/core/settings.py`): `MODEL_MAIN`, `MODEL_REALTIME`, `TTS_MODEL`, `TTS_VOICE`, `TTS_INSTRUCTIONS`, `RAG_MAX_RESULTS`, `VS_NAME`.

Optional **vector store ids** (same names as environment variables; copied into the process env at startup when the OS variable is unset): `VECTOR_STORE_ID_VEHICLE_CATALOG`, `VECTOR_STORE_ID_DEALERSHIP_FAQ`, `VECTOR_STORE_ID_SHOWROOM_LAYOUTS`. Example:

```json
{
  "OPENAI_API_KEY": "sk-...",
  "VECTOR_STORE_ID_VEHICLE_CATALOG": "vs_xxxxxxxx",
  "VECTOR_STORE_ID_DEALERSHIP_FAQ": "vs_xxxxxxxx",
  "VECTOR_STORE_ID_SHOWROOM_LAYOUTS": "vs_xxxxxxxx"
}
```

Alternatively, set environment variables; for keys other than `OPENAI_API_KEY`, env wins over JSON when non-empty. For `OPENAI_API_KEY`, a non-empty value in `local.settings.json` wins over env. For `VECTOR_STORE_ID_*`, a non-empty **OS** env wins; otherwise JSON supplies the value.

Do not commit secrets.

## Install

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

Editable install (`-e .`) adds the `showroom` package from `src/` so imports work from any working directory.

## Run

**Streamlit** (from repo root):

```bash
streamlit run front-end/app.py
```

**FastAPI bridge** (from repo root):

```bash
python server.py
```

Open `http://localhost:8000` for the standalone voice page.

### Vector store IDs per file

Filename → environment variable (see **Vector index** above for resolution order and export script):

- `vehicle_catalog.txt` → `VECTOR_STORE_ID_VEHICLE_CATALOG`
- `dealership_faq.txt` → `VECTOR_STORE_ID_DEALERSHIP_FAQ`
- `showroom_layouts.txt` → `VECTOR_STORE_ID_SHOWROOM_LAYOUTS`

## Layout

| Path | Role |
|------|------|
| `front-end/app.py` | Streamlit application |
| `front-end/voice_component.py` | Streamlit voice widget (HTML/JS) |
| `front-end/voice.html` | Standalone voice client |
| `server.py` | Thin launcher; runs `showroom.presentation.server:app` |
| `src/showroom/core/` | Settings (`local.settings.json`, env) |
| `src/showroom/helpers/` | e.g. `RepositoryPaths.root()` |
| `src/showroom/domain/` | Pydantic contracts (`ShowroomResponse`) |
| `src/showroom/agents/` | `factory` façade, `graph/` composition, `prompts/` per agent, `tools/` (FileSearchTool wrappers), `definitions` |
| `src/showroom/rag/` | `domain/` (corpus ids), `application/services/`, `infrastructure/openai/` (vector store lifecycle + file attributes) |
| `src/showroom/infrastructure/` | ``OpenAIProvider`` (sync vector store / Files API for RAG), ``OpenAIRealtimeSessionsClient`` + ``VoiceWidgetEphemeralCredentialsIssuer`` (Realtime HTTP, decoupled from UI) |
| `src/showroom/presentation/` | FastAPI app |
| `tests/` | Smoke tests |
| `data/*.txt` | RAG corpus |

## Architecture

See [documents/ARQUITECTURA_SHOWROOM_VIRTUAL.md](documents/ARQUITECTURA_SHOWROOM_VIRTUAL.md).

## Tests

```bash
python -m unittest tests.test_showroom_imports
```
