"""OpenAI-specific RAG infrastructure (vector store lifecycle, file attributes)."""

from showroom.rag.infrastructure.openai.file_attributes import (
    SHOWROOM_CORPUS_ATTR_KEY,
    ensure_showroom_corpus_attributes_sync,
)
from showroom.rag.infrastructure.openai.lifecycle import OpenAIVectorIndexLifecycle

__all__ = [
    "OpenAIVectorIndexLifecycle",
    "SHOWROOM_CORPUS_ATTR_KEY",
    "ensure_showroom_corpus_attributes_sync",
]
