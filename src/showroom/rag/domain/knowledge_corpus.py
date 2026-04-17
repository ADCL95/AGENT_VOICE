"""
Showroom RAG corpus: knowledge filenames and environment keys (no I/O).

Single source of truth for provisioning order and specialist ``file_search`` routing.
"""

from __future__ import annotations

from typing import Final

KNOWLEDGE_TXT_BASENAMES: Final[tuple[str, ...]] = (
    "vehicle_catalog.txt",
    "dealership_faq.txt",
    "showroom_layouts.txt",
)

VECTOR_STORE_ENV_BY_FILENAME: Final[dict[str, str]] = {
    "vehicle_catalog.txt": "VECTOR_STORE_ID_VEHICLE_CATALOG",
    "dealership_faq.txt": "VECTOR_STORE_ID_DEALERSHIP_FAQ",
    "showroom_layouts.txt": "VECTOR_STORE_ID_SHOWROOM_LAYOUTS",
}

EXPECTED_KNOWLEDGE_BASENAMES: Final[frozenset[str]] = frozenset(KNOWLEDGE_TXT_BASENAMES)
