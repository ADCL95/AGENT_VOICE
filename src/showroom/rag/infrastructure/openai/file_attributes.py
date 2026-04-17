"""
OpenAI vector store file attributes for specialist-scoped ``file_search``.

When all corpora share one vector store, ``FileSearchTool`` filters on ``showroom_corpus``.
This module stamps that attribute from the Files API basename.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from showroom.rag.domain.knowledge_corpus import EXPECTED_KNOWLEDGE_BASENAMES

if TYPE_CHECKING:
    from openai import OpenAI

logger = logging.getLogger(__name__)

SHOWROOM_CORPUS_ATTR_KEY: Final[str] = "showroom_corpus"


def _iter_vector_store_files(client: OpenAI, vector_store_id: str):
    page = client.vector_stores.files.list(vector_store_id=vector_store_id, limit=100)
    while True:
        yield from page.data
        if not page.has_next_page():
            break
        page = page.next_page()


def ensure_showroom_corpus_attributes_sync(client: OpenAI, vector_store_id: str) -> None:
    """
    Ensure each showroom knowledge file in the store carries ``showroom_corpus`` = basename.

    Safe to call repeatedly; updates only when missing or incorrect.
    """
    for vs_file in _iter_vector_store_files(client, vector_store_id):
        if vs_file.status != "completed":
            logger.info(
                "vector_store_file_skip_attr vector_store_id=%s file_id=%s status=%s",
                vector_store_id,
                vs_file.id,
                vs_file.status,
            )
            continue
        try:
            file_obj = client.files.retrieve(vs_file.id)
        except Exception:
            logger.exception(
                "vector_store_file_attr_lookup_failed vector_store_id=%s file_id=%s",
                vector_store_id,
                vs_file.id,
            )
            raise
        basename = file_obj.filename or ""
        if basename not in EXPECTED_KNOWLEDGE_BASENAMES:
            logger.warning(
                "vector_store_file_unexpected_corpus vector_store_id=%s file_id=%s filename=%r",
                vector_store_id,
                vs_file.id,
                basename,
            )
            continue
        current = dict(vs_file.attributes or {})
        if current.get(SHOWROOM_CORPUS_ATTR_KEY) == basename:
            continue
        merged = {**current, SHOWROOM_CORPUS_ATTR_KEY: basename}
        try:
            client.vector_stores.files.update(
                vs_file.id,
                vector_store_id=vector_store_id,
                attributes=merged,
            )
        except Exception:
            logger.exception(
                "vector_store_file_attr_update_failed vector_store_id=%s file_id=%s",
                vector_store_id,
                vs_file.id,
            )
            raise
        logger.info(
            "vector_store_file_attr_set vector_store_id=%s file_id=%s %s=%r",
            vector_store_id,
            vs_file.id,
            SHOWROOM_CORPUS_ATTR_KEY,
            basename,
        )
