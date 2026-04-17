"""
OpenAI Vector Store lifecycle for showroom knowledge files.

Uploads each ``data/*.txt`` via the Files API, attaches with ``file_batches``, and polls
until each vector store file is ``completed``. Used by ``VectorStoreService``.

Provisioning uses the synchronous ``OpenAI`` client; ``ensure_index_id_async`` delegates
to ``ensure_index_ids_sync`` via ``asyncio.to_thread`` for asyncio servers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
import time
from typing import TYPE_CHECKING, Literal

from showroom.core.settings import get_settings
from showroom.infrastructure.openai_client import OpenAIProvider
from showroom.rag.domain.knowledge_corpus import VECTOR_STORE_ENV_BY_FILENAME

if TYPE_CHECKING:
    from openai import OpenAI

logger = logging.getLogger(__name__)


class OpenAIVectorIndexLifecycle:
    """
    Creates or reuses one OpenAI Vector Store per knowledge ``.txt`` file.

    Used by ``VectorStoreService`` for provisioning and id discovery.
    """

    __slots__ = ("_client_provider",)
    _POLL_INTERVAL_SECONDS = 8
    _UPLOAD_TIMEOUT_SECONDS = 900

    def __init__(self, client_provider: type[OpenAIProvider] = OpenAIProvider) -> None:
        self._client_provider = client_provider

    def _client(self) -> OpenAI:
        return self._client_provider.instance()

    @staticmethod
    def _manifest_path(cache_file: str) -> Path:
        return Path(cache_file)

    @classmethod
    def _load_cached_ids(cls, cache_file: str) -> dict[str, str]:
        path = cls._manifest_path(cache_file)
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"shared_legacy_store": raw}
        if not isinstance(parsed, dict):
            return {}
        out: dict[str, str] = {}
        for k, v in parsed.items():
            if isinstance(k, str) and isinstance(v, str) and v.strip():
                out[k] = v.strip()
        return out

    @classmethod
    def _save_cached_ids(cls, cache_file: str, ids_by_file: dict[str, str]) -> None:
        with open(cls._manifest_path(cache_file), "w", encoding="utf-8") as f:
            json.dump(ids_by_file, f, indent=2)

    def _normalize_cached_manifest(self, cached: dict[str, str]) -> dict[str, str]:
        """
        Expand a single-line legacy manifest (``shared_legacy_store``) when that vector
        store already holds all knowledge files (``completed`` count >= corpus size).
        """
        if len(cached) != 1 or "shared_legacy_store" not in cached:
            return cached
        vs_id = cached["shared_legacy_store"]
        try:
            vs = self._client().vector_stores.retrieve(vs_id)
        except Exception:
            return cached
        need = len(VECTOR_STORE_ENV_BY_FILENAME)
        if vs.file_counts.completed < need:
            return cached
        return {name: vs_id for name in VECTOR_STORE_ENV_BY_FILENAME}

    def _vector_store_is_valid(self, vs_id: str) -> bool:
        client = self._client()
        try:
            vs = client.vector_stores.retrieve(vs_id)
            return vs.file_counts.completed > 0
        except Exception:
            return False

    def _poll_batch_until_terminal(
        self,
        *,
        vector_store_id: str,
        batch_id: str,
        filename: str,
        deadline_monotonic: float,
    ):
        client = self._client()
        started = time.monotonic()
        while True:
            elapsed = int(time.monotonic() - started)
            batch = client.vector_stores.file_batches.retrieve(
                vector_store_id=vector_store_id,
                batch_id=batch_id,
            )
            logger.info(
                "vector_store_poll filename=%s vector_store_id=%s batch_id=%s elapsed_s=%s status=%s counts=%s",
                filename,
                vector_store_id,
                batch_id,
                elapsed,
                batch.status,
                batch.file_counts,
            )
            if batch.status in ("completed", "failed", "cancelled"):
                return batch
            if time.monotonic() >= deadline_monotonic:
                raise TimeoutError(
                    f"Timed out waiting for batch {batch_id} "
                    f"(filename={filename}, vector_store_id={vector_store_id})"
                )
            time.sleep(self._POLL_INTERVAL_SECONDS)

    def _vector_store_file_poll_once(
        self,
        client: OpenAI,
        *,
        vector_store_id: str,
        file_id: str,
        filename: str,
        started_monotonic: float,
    ) -> Literal["completed", "failed", "cancelled", "in_progress"]:
        vs_file = client.vector_stores.files.retrieve(
            file_id,
            vector_store_id=vector_store_id,
        )
        elapsed = int(time.monotonic() - started_monotonic)
        logger.info(
            "vector_store_file_poll filename=%s vector_store_id=%s file_id=%s "
            "elapsed_s=%s status=%s usage_bytes=%s",
            filename,
            vector_store_id,
            file_id,
            elapsed,
            vs_file.status,
            vs_file.usage_bytes,
        )
        if vs_file.status == "completed":
            return "completed"
        if vs_file.status == "failed":
            last_error = getattr(vs_file, "last_error", None)
            detail = f"{last_error.code}: {last_error.message}" if last_error else "unknown"
            raise RuntimeError(
                f"Vector store file ingestion failed for {filename} "
                f"(vector_store_id={vector_store_id}, file_id={file_id}): {detail}"
            )
        if vs_file.status == "cancelled":
            raise RuntimeError(
                f"Vector store file ingestion cancelled for {filename} "
                f"(vector_store_id={vector_store_id}, file_id={file_id})"
            )
        return "in_progress"

    def _poll_vector_store_files_until_completed(
        self,
        *,
        vector_store_id: str,
        file_ids: list[str],
        filename: str,
        deadline_monotonic: float,
    ) -> None:
        client = self._client()
        pending = set(file_ids)
        started = time.monotonic()
        while pending:
            if time.monotonic() >= deadline_monotonic:
                files_diag = self._describe_vector_store_files(vector_store_id)
                raise TimeoutError(
                    f"Timed out waiting for vector store file ingestion "
                    f"(filename={filename}, vector_store_id={vector_store_id}, pending={sorted(pending)}). "
                    f"files={files_diag}"
                )
            for file_id in pending.copy():
                outcome = self._vector_store_file_poll_once(
                    client,
                    vector_store_id=vector_store_id,
                    file_id=file_id,
                    filename=filename,
                    started_monotonic=started,
                )
                if outcome == "completed":
                    pending.discard(file_id)
            if pending:
                time.sleep(self._POLL_INTERVAL_SECONDS)

    def _describe_vector_store_files(self, vector_store_id: str) -> str:
        client = self._client()
        page = client.vector_stores.files.list(
            vector_store_id=vector_store_id,
            limit=20,
        )
        lines: list[str] = []
        for item in page.data:
            last_error = getattr(item, "last_error", None)
            err = f"{last_error.code}:{last_error.message}" if last_error else "none"
            lines.append(
                f"{item.id} status={item.status} usage_bytes={item.usage_bytes} last_error={err}"
            )
        return "; ".join(lines) if lines else "no files attached"

    def _upload_single_file_with_timeout(
        self,
        *,
        vector_store_id: str,
        file_path: str,
        filename: str,
    ) -> None:
        client = self._client()
        deadline = time.monotonic() + float(self._UPLOAD_TIMEOUT_SECONDS)
        with open(file_path, "rb") as stream:
            file_obj = client.files.create(file=stream, purpose="assistants")

        batch = client.vector_stores.file_batches.create(
            vector_store_id=vector_store_id,
            file_ids=[file_obj.id],
        )
        logger.info(
            "vector_store_upload_started filename=%s vector_store_id=%s file_id=%s batch_id=%s",
            filename,
            vector_store_id,
            file_obj.id,
            batch.id,
        )
        try:
            terminal_batch = self._poll_batch_until_terminal(
                vector_store_id=vector_store_id,
                batch_id=batch.id,
                filename=filename,
                deadline_monotonic=deadline,
            )
        except Exception:
            files_diag = self._describe_vector_store_files(vector_store_id)
            logger.exception(
                "vector_store_upload_timeout_or_error filename=%s vector_store_id=%s files=%s",
                filename,
                vector_store_id,
                files_diag,
            )
            raise

        if terminal_batch.status != "completed":
            files_diag = self._describe_vector_store_files(vector_store_id)
            raise RuntimeError(
                f"Vector store file batch finished with status={terminal_batch.status} "
                f"for {filename} (vector_store_id={vector_store_id}, batch_id={batch.id}). "
                f"files={files_diag}"
            )

        self._poll_vector_store_files_until_completed(
            vector_store_id=vector_store_id,
            file_ids=[file_obj.id],
            filename=filename,
            deadline_monotonic=deadline,
        )

    def ensure_index_ids_sync(self) -> list[str]:
        """
        Create or validate vector stores for each knowledge file (blocking, sync OpenAI).

        Prefer this from Streamlit / scripts; use ``ensure_index_id_async`` from asyncio servers.
        """
        settings = get_settings()
        client = self._client()

        kb_files = [
            settings.vehicle_catalog,
            settings.dealership_faq,
            settings.showroom_layouts,
        ]
        missing = [p for p in kb_files if not os.path.exists(p)]
        if missing:
            raise FileNotFoundError(
                f"Knowledge base files not found: {missing}\n"
                f"Expected under: {os.path.dirname(kb_files[0])}"
            )

        cached = self._normalize_cached_manifest(self._load_cached_ids(settings.vs_id_file))
        ids_by_file: dict[str, str] = {}
        for path in kb_files:
            filename = os.path.basename(path)
            env_key = VECTOR_STORE_ENV_BY_FILENAME.get(filename)
            env_id = os.environ.get(env_key) if env_key else None
            if env_id and self._vector_store_is_valid(env_id):
                ids_by_file[filename] = env_id
                logger.info("vector_store_reuse filename=%s vector_store_id=%s source=env", filename, env_id)
                continue
            cached_id = cached.get(filename)
            if cached_id and self._vector_store_is_valid(cached_id):
                ids_by_file[filename] = cached_id
                logger.info("vector_store_reuse filename=%s vector_store_id=%s source=manifest", filename, cached_id)
                continue

            logger.info("vector_store_create filename=%s", filename)
            vs = client.vector_stores.create(name=f"{settings.vs_name} :: {filename}")
            self._upload_single_file_with_timeout(
                vector_store_id=vs.id,
                file_path=path,
                filename=filename,
            )
            ids_by_file[filename] = vs.id
            logger.info("vector_store_ready filename=%s vector_store_id=%s", filename, vs.id)

        for filename, env_key in VECTOR_STORE_ENV_BY_FILENAME.items():
            vs_id = ids_by_file.get(filename)
            if vs_id:
                os.environ[env_key] = vs_id
        os.environ["VECTOR_STORE_IDS"] = ",".join(
            ids_by_file[os.path.basename(path)] for path in kb_files
        )

        self._save_cached_ids(settings.vs_id_file, ids_by_file)
        return [ids_by_file[os.path.basename(path)] for path in kb_files]

    async def ensure_index_id_async(self) -> list[str]:
        """Async wrapper: runs sync provisioning in a worker thread (non-blocking I/O loop)."""
        return await asyncio.to_thread(self.ensure_index_ids_sync)
