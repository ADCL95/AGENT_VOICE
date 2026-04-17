"""
Vector index lifecycle facade (application service).

Delegates to ``OpenAIVectorIndexLifecycle`` (OpenAI Vector Store + Files API).
"""

from __future__ import annotations

import asyncio

import nest_asyncio

from showroom.rag.infrastructure.openai import OpenAIVectorIndexLifecycle

nest_asyncio.apply()


class VectorStoreService:
    """
    Application entry for “ensure we have vector index ids”.

    Pass a custom ``OpenAIVectorIndexLifecycle`` only for tests (subclass/mocks).
    """

    __slots__ = ("_backend",)

    _default: VectorStoreService | None = None

    def __init__(self, backend: OpenAIVectorIndexLifecycle | None = None) -> None:
        self._backend = backend if backend is not None else OpenAIVectorIndexLifecycle()

    @classmethod
    def default(cls) -> VectorStoreService:
        """Process-wide default service (lazy singleton)."""
        if cls._default is None:
            cls._default = cls(backend=OpenAIVectorIndexLifecycle())
        return cls._default

    async def ensure_async(self) -> list[str]:
        return await self._backend.ensure_index_id_async()

    def ensure_sync(self) -> list[str]:
        """Synchronous entry (Streamlit / nested event loops via nest_asyncio)."""
        sync_fn = getattr(self._backend, "ensure_index_ids_sync", None)
        if callable(sync_fn):
            return sync_fn()
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.ensure_async())
        except RuntimeError:
            return asyncio.run(self.ensure_async())
