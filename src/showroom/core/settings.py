"""
Application settings: env vars and local.settings.json at repo root.

Priority: for ``OPENAI_API_KEY``, a non-empty value in ``local.settings.json`` wins over
the environment (so a real key in the file is not shadowed by an empty or placeholder
``OPENAI_API_KEY`` in the shell). Other keys still use environment first, then JSON.

Vector store IDs for RAG (``VECTOR_STORE_ID_*``): a **non-empty** OS environment variable
wins; otherwise, if the same key is present in ``local.settings.json``, it is copied into
``os.environ`` at import time so ``OpenAIVectorIndexLifecycle`` reuses stores without a
shell export. See README for names.
Implements a typed **Settings** object (single loaded instance) plus module-level
aliases for convenient imports (e.g. ``from showroom.core.settings import OPENAI_API_KEY``).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from showroom.helpers.paths import RepositoryPaths


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Immutable application configuration loaded once at import time."""

    openai_api_key: str
    model_main: str
    model_realtime: str
    tts_model: str
    tts_voice: str
    tts_instructions: str
    base_dir: str
    data_dir: str
    vs_id_file: str
    vehicle_catalog: str
    dealership_faq: str
    showroom_layouts: str
    rag_max_results: int
    vs_name: str
    intents: tuple[str, ...]

    @classmethod
    def load(cls) -> AppSettings:
        """Load settings from environment and ``local.settings.json`` (Template Method entry)."""
        root = RepositoryPaths.root()
        settings_path = root / "local.settings.json"
        file_values = cls._read_json_file(settings_path)
        cls._apply_vector_store_ids_to_process_env(file_values)
        api_key = cls._resolve_openai_api_key(file_values)
        if not api_key:
            if not settings_path.is_file():
                detail = (
                    f"Expected secrets file at {settings_path} (missing). "
                    "Create `local.settings.json` in the repo root (see README.md for keys) "
                    "with `OPENAI_API_KEY`, or set the environment variable OPENAI_API_KEY."
                )
            else:
                detail = (
                    f"{settings_path} exists but OPENAI_API_KEY is empty. "
                    "Paste your key from https://platform.openai.com/api-keys into that JSON field "
                    "or set the environment variable OPENAI_API_KEY."
                )
            raise RuntimeError(detail)
        model_main = cls._resolve_str("MODEL_MAIN", "gpt-4o-mini", file_values)
        model_realtime = cls._resolve_str("MODEL_REALTIME", "gpt-4o-realtime-preview", file_values)
        tts_model = cls._resolve_str("TTS_MODEL", "gpt-4o-mini-tts", file_values)
        tts_voice = cls._resolve_str("TTS_VOICE", "marin", file_values)
        tts_instructions = cls._resolve_str(
            "TTS_INSTRUCTIONS",
            "Speak clearly and warmly, like a luxury showroom host.",
            file_values,
        )
        rag_max_results = cls._resolve_int("RAG_MAX_RESULTS", 5, file_values)
        vs_name = cls._resolve_str(
            "VS_NAME",
            "Aether Motors — Showroom Knowledge Base",
            file_values,
        )
        base = str(root)
        data = str(root / "data")
        return cls(
            openai_api_key=api_key,
            model_main=model_main,
            model_realtime=model_realtime,
            tts_model=tts_model,
            tts_voice=tts_voice,
            tts_instructions=tts_instructions,
            base_dir=base,
            data_dir=data,
            vs_id_file=str(root / ".vector_store_id"),
            vehicle_catalog=str(root / "data" / "vehicle_catalog.txt"),
            dealership_faq=str(root / "data" / "dealership_faq.txt"),
            showroom_layouts=str(root / "data" / "showroom_layouts.txt"),
            rag_max_results=rag_max_results,
            vs_name=vs_name,
            intents=(
                "product_info",
                "space_analysis",
                "purchase_intent",
                "voice_request",
                "escalation",
            ),
        )

    @staticmethod
    def _apply_vector_store_ids_to_process_env(file_values: dict[str, Any]) -> None:
        """Populate ``os.environ`` with optional vector store ids from JSON (local dev).

        ``OpenAIVectorIndexLifecycle`` reads ``VECTOR_STORE_ID_*`` from the environment
        before the ``.vector_store_id`` manifest. Existing non-empty env values win.
        """
        from showroom.rag.domain.knowledge_corpus import VECTOR_STORE_ENV_BY_FILENAME

        for _filename, env_key in VECTOR_STORE_ENV_BY_FILENAME.items():
            if os.environ.get(env_key, "").strip():
                continue
            file_val = file_values.get(env_key)
            if file_val is None or str(file_val).strip() == "":
                continue
            os.environ[env_key] = str(file_val).strip()

    @staticmethod
    def _read_json_file(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        with open(path, encoding="utf-8-sig") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return {}
        # Uppercase keys so ``openai_api_key`` and ``OPENAI_API_KEY`` both work (JSON is case-sensitive).
        out: dict[str, Any] = {}
        for k, v in raw.items():
            if isinstance(k, str):
                nk = k.lstrip("\ufeff").strip().upper()
            else:
                nk = str(k)
            out[nk] = v
        return out

    @staticmethod
    def _resolve_openai_api_key(file_values: dict[str, Any]) -> str:
        """JSON first (non-empty), then env — avoids a blank or dummy ``OPENAI_API_KEY`` in the shell hiding the file."""
        file_val = file_values.get("OPENAI_API_KEY")
        if file_val is not None and str(file_val).strip() != "":
            return str(file_val).strip()
        env_val = os.environ.get("OPENAI_API_KEY")
        if env_val is not None and str(env_val).strip() != "":
            return str(env_val).strip()
        return ""

    @staticmethod
    def _resolve_str(key: str, default: str, file_values: dict[str, Any]) -> str:
        env_val = os.environ.get(key)
        if env_val is not None and str(env_val).strip() != "":
            return str(env_val).strip()
        file_val = file_values.get(key)
        if file_val is not None and str(file_val).strip() != "":
            return str(file_val).strip()
        return default

    @staticmethod
    def _resolve_int(key: str, default: int, file_values: dict[str, Any]) -> int:
        env_val = os.environ.get(key)
        if env_val is not None and str(env_val).strip() != "":
            return int(env_val)
        file_val = file_values.get(key)
        if file_val is not None and str(file_val).strip() != "":
            return int(file_val)
        return default


_SETTINGS = AppSettings.load()


def get_settings() -> AppSettings:
    """Return the process-wide loaded settings (singleton accessor)."""
    return _SETTINGS


# Module-level aliases (backward compatible imports for presentation and front-end)
OPENAI_API_KEY = _SETTINGS.openai_api_key
MODEL_MAIN = _SETTINGS.model_main
MODEL_REALTIME = _SETTINGS.model_realtime
TTS_MODEL = _SETTINGS.tts_model
TTS_VOICE = _SETTINGS.tts_voice
TTS_INSTRUCTIONS = _SETTINGS.tts_instructions
BASE_DIR = _SETTINGS.base_dir
DATA_DIR = _SETTINGS.data_dir
VS_ID_FILE = _SETTINGS.vs_id_file
VEHICLE_CATALOG = _SETTINGS.vehicle_catalog
DEALERSHIP_FAQ = _SETTINGS.dealership_faq
SHOWROOM_LAYOUTS = _SETTINGS.showroom_layouts
RAG_MAX_RESULTS = _SETTINGS.rag_max_results
VS_NAME = _SETTINGS.vs_name
INTENTS = list(_SETTINGS.intents)
