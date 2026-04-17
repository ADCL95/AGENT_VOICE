"""
Hosted ``file_search`` toolset backed by OpenAI Vector Stores.

``FileSearchTool`` maps to the Responses API hosted ``file_search`` tool. Specialists
receive **one** tool each, scoped to their corpus:

- **Split index** (one vector store id per ``data/*.txt``): each tool passes a single
  ``vector_store_id`` matching the lifecycle order
  ``vehicle_catalog → dealership_faq → showroom_layouts``.
- **Shared vector store** (same id three times after manifest normalization): tools
  share the store id and apply a comparison filter on ``showroom_corpus`` (file
  attributes ensured at graph build — see ``ensure_showroom_corpus_attributes_sync``).
"""

from __future__ import annotations

import logging

from agents import FileSearchTool
from openai.types.responses.file_search_tool_param import Filters

from showroom.infrastructure.openai_client import OpenAIProvider
from showroom.rag.domain.knowledge_corpus import KNOWLEDGE_TXT_BASENAMES
from showroom.rag.infrastructure.openai import (
    SHOWROOM_CORPUS_ATTR_KEY,
    ensure_showroom_corpus_attributes_sync,
)

logger = logging.getLogger(__name__)


class ShowroomVectorStoreToolSet:
    """
    Produces hosted ``FileSearchTool`` instances for specialist agents.

    Each specialist gets exactly one ``file_search`` tool bound to its knowledge file.
    """

    __slots__ = ("_ids", "_max_results", "_merged_single_store_id")

    def __init__(self, vector_store_ids: list[str], max_results: int) -> None:
        if len(vector_store_ids) != len(KNOWLEDGE_TXT_BASENAMES):
            raise ValueError(
                f"Expected {len(KNOWLEDGE_TXT_BASENAMES)} vector store slots "
                f"(vehicle, faq, layouts); got {len(vector_store_ids)}."
            )
        self._ids = list(vector_store_ids)
        self._max_results = max_results
        unique = set(self._ids)
        self._merged_single_store_id: str | None = (
            self._ids[0] if len(unique) == 1 else None
        )
        if self._merged_single_store_id is not None:
            try:
                ensure_showroom_corpus_attributes_sync(
                    OpenAIProvider.instance(),
                    self._merged_single_store_id,
                )
            except Exception:
                logger.exception(
                    "rag_corpus_attributes_failed component=rag vector_store_id=%s",
                    self._merged_single_store_id,
                )
                raise

    def build_product_tools(self) -> list[FileSearchTool]:
        return [self._tool_for_corpus(KNOWLEDGE_TXT_BASENAMES[0], store_slot=0)]

    def build_space_tools(self) -> list[FileSearchTool]:
        return [self._tool_for_corpus(KNOWLEDGE_TXT_BASENAMES[2], store_slot=2)]

    def build_purchase_tools(self) -> list[FileSearchTool]:
        return [self._tool_for_corpus(KNOWLEDGE_TXT_BASENAMES[1], store_slot=1)]

    def _tool_for_corpus(self, corpus_basename: str, *, store_slot: int) -> FileSearchTool:
        if self._merged_single_store_id is not None:
            vs_id = self._merged_single_store_id
            filters: Filters | None = {
                "type": "eq",
                "key": SHOWROOM_CORPUS_ATTR_KEY,
                "value": corpus_basename,
            }
        else:
            vs_id = self._ids[store_slot]
            filters = None
        return FileSearchTool(
            vector_store_ids=[vs_id],
            max_num_results=self._max_results,
            include_search_results=True,
            filters=filters,
        )
