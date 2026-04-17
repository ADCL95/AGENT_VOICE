"""RAG domain: corpus identifiers (no OpenAI / no filesystem I/O)."""

from showroom.rag.domain.knowledge_corpus import (
    EXPECTED_KNOWLEDGE_BASENAMES,
    KNOWLEDGE_TXT_BASENAMES,
    VECTOR_STORE_ENV_BY_FILENAME,
)

__all__ = [
    "EXPECTED_KNOWLEDGE_BASENAMES",
    "KNOWLEDGE_TXT_BASENAMES",
    "VECTOR_STORE_ENV_BY_FILENAME",
]
