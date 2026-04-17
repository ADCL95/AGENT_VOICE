"""
Smoke-test RAG: ensure vector store ids, then one Responses API ``file_search`` call.

Usage (repo root, PYTHONPATH=src or ``pip install -e .``):

    python scripts/smoke_rag.py
    python scripts/smoke_rag.py --skip-provision   # uses VECTOR_STORE_IDS env (comma-separated)

Exits 0 when provisioning (unless skipped) and the retrieval response return non-empty text.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path


def _repo_src_on_path() -> None:
    root = Path(__file__).resolve().parents[1]
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def main() -> int:
    _repo_src_on_path()
    parser = argparse.ArgumentParser(description="RAG smoke: vector stores + file_search")
    parser.add_argument(
        "--skip-provision",
        action="store_true",
        help="Skip ensure_index_ids_sync; set VECTOR_STORE_IDS to three comma-separated vs ids.",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Less logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    from showroom.core.settings import get_settings
    from showroom.infrastructure.openai_client import OpenAIProvider
    from showroom.rag.infrastructure.openai import OpenAIVectorIndexLifecycle

    settings = get_settings()
    ids: list[str]
    if args.skip_provision:
        raw = os.environ.get("VECTOR_STORE_IDS", "").strip()
        if not raw:
            print("ERROR: set VECTOR_STORE_IDS=vs1,vs2,vs3 when using --skip-provision", file=sys.stderr)
            return 1
        ids = [x.strip() for x in raw.split(",") if x.strip()]
        if len(ids) != 3:
            print("ERROR: VECTOR_STORE_IDS must contain exactly three vector store ids", file=sys.stderr)
            return 1
        print("Using VECTOR_STORE_IDS from environment (skip provision).")
    else:
        print("Provisioning / validating vector stores (sync OpenAI client)...", flush=True)
        ids = OpenAIVectorIndexLifecycle().ensure_index_ids_sync()
        print("Vector store ids:", ids, flush=True)

    client = OpenAIProvider.instance()
    print("Calling Responses API file_search...", flush=True)
    try:
        resp = client.responses.create(
            model=settings.model_main,
            input=(
                "Using only the attached knowledge bases: cite one vehicle model with a trim name "
                "and an indicative price or range from the catalog."
            ),
            tools=[
                {
                    "type": "file_search",
                    "vector_store_ids": ids,
                    "max_num_results": settings.rag_max_results,
                }
            ],
            include=["file_search_call.results"],
            max_output_tokens=400,
        )
    except Exception as e:
        logging.exception("responses.create failed")
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    text = (resp.output_text or "").strip()
    if not text:
        print("ERROR: empty model output_text", file=sys.stderr)
        return 1
    print("--- model output (truncated) ---")
    print(text[:1200] + ("..." if len(text) > 1200 else ""))
    print("--- smoke_rag OK ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
