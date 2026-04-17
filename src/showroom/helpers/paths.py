"""Repository path resolution (single source for repo root)."""

from __future__ import annotations

from pathlib import Path


class RepositoryPaths:
    """
    Resolves filesystem locations relative to the repository root.

    Stateless path helper (no I/O); keeps path logic off random module-level callables.
    """

    __slots__ = ()

    @classmethod
    def root(cls) -> Path:
        """
        Repository root (contains ``src/``, ``front-end/``, ``data/``).

        Resolved from ``src/showroom/helpers/paths.py`` → ``parents[3]``.
        """
        return Path(__file__).resolve().parents[3]
