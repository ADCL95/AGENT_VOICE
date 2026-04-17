"""
Create/reuse vector stores and export their IDs as environment variables.

Usage (repo root):
    python scripts/export_vector_store_env.py
    python scripts/export_vector_store_env.py --persist-user-env
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import time
from pathlib import Path

from showroom.core.settings import get_settings
from showroom.rag.infrastructure.openai import OpenAIVectorIndexLifecycle


def _print_session_exports(mapping: dict[str, str]) -> None:
    print("\nPowerShell (current session):")
    for key, value in mapping.items():
        print(f'$env:{key} = "{value}"')


def _persist_user_env(mapping: dict[str, str]) -> None:
    for key, value in mapping.items():
        subprocess.run(["setx", key, value], check=False, capture_output=True)


async def _with_progress(coro: asyncio.Future, *, step: str, interval_s: int = 8) -> list[str]:
    started = time.monotonic()
    task = asyncio.create_task(coro)
    while not task.done():
        elapsed = int(time.monotonic() - started)
        print(f"[{step}] running... {elapsed}s", flush=True)
        await asyncio.sleep(interval_s)
    return await task


async def _main_async(persist_user_env: bool, timeout_s: int) -> int:
    settings = get_settings()
    lifecycle = OpenAIVectorIndexLifecycle()
    print("Ensuring vector stores (one per file in data/) ...", flush=True)
    try:
        ids = await asyncio.wait_for(
            _with_progress(
                lifecycle.ensure_index_id_async(),
                step="OpenAI vector store provisioning",
            ),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        print(
            f"Timeout after {timeout_s}s while waiting for OpenAI vector store provisioning.",
            flush=True,
        )
        print("Try again with a larger timeout: --timeout-seconds 1800", flush=True)
        return 1

    filenames = [
        Path(settings.vehicle_catalog).name,
        Path(settings.dealership_faq).name,
        Path(settings.showroom_layouts).name,
    ]
    env_keys = [
        "VECTOR_STORE_ID_VEHICLE_CATALOG",
        "VECTOR_STORE_ID_DEALERSHIP_FAQ",
        "VECTOR_STORE_ID_SHOWROOM_LAYOUTS",
    ]

    mapping = dict(zip(env_keys, ids, strict=True))
    mapping["VECTOR_STORE_IDS"] = ",".join(ids)

    print("Vector store IDs ready:")
    for filename, env_key, vs_id in zip(filenames, env_keys, ids, strict=True):
        print(f"- {filename}: {vs_id}  ({env_key})")

    manifest_path = Path(settings.vs_id_file)
    print(f"\nManifest cache: {manifest_path}")
    print(manifest_path.read_text(encoding="utf-8"))

    _print_session_exports(mapping)

    if persist_user_env:
        _persist_user_env(mapping)
        print("\nPersisted user environment variables with setx.")
        print("Open a NEW terminal to see persisted values.")
    else:
        print("\nTip: add --persist-user-env to store them permanently (user scope).")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--persist-user-env",
        action="store_true",
        help="Persist ids with setx (user-level Windows environment variables).",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=900,
        help="Max wait for OpenAI provisioning (default: 900).",
    )
    args = parser.parse_args()
    return asyncio.run(
        _main_async(
            persist_user_env=args.persist_user_env,
            timeout_s=args.timeout_seconds,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
