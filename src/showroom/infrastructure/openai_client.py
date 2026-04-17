"""Shared synchronous OpenAI client for vector store and Files API (RAG lifecycle)."""

from __future__ import annotations

from threading import Lock
from typing import ClassVar

from openai import OpenAI

from showroom.core.settings import get_settings


class OpenAIProvider:
    """
    Provides a single synchronous ``OpenAI`` client for vector store / Files API work.

    Matches the official snippets (``client = OpenAI()``); used under ``showroom.rag``.
    """

    __slots__ = ()
    _instance: ClassVar[OpenAI | None] = None
    _lock: ClassVar[Lock] = Lock()

    @classmethod
    def instance(cls) -> OpenAI:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    key = get_settings().openai_api_key
                    cls._instance = OpenAI(api_key=key)
        return cls._instance
