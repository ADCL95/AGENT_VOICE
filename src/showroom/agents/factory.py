"""Factory for the OpenAI Agents SDK showroom orchestration graph."""

from __future__ import annotations

from typing import Any

from showroom.agents.graph.multi_agent_system import ShowroomOpenAIAgentGraphBuilder


class OpenAIAgentSystemFactory:
    """Builds the OpenAI Agents SDK orchestrator + specialists graph."""

    __slots__ = ()

    _default: OpenAIAgentSystemFactory | None = None

    @classmethod
    def default(cls) -> OpenAIAgentSystemFactory:
        """Shared factory instance (optional singleton for DI simplicity)."""
        if cls._default is None:
            cls._default = cls()
        return cls._default

    def build(self, vector_store_ids: list[str]) -> Any:
        """
        Build the full multi-agent OpenAI Agents SDK graph.

        Args:
            vector_store_ids: Three OpenAI vector store ids in lifecycle order
                (``vehicle_catalog.txt``, ``dealership_faq.txt``, ``showroom_layouts.txt``).
                If all three entries are the same id (shared store), each specialist tool
                scopes retrieval with a ``showroom_corpus`` attribute filter.

        Returns:
            Orchestrator ``Agent`` ready for ``Runner.run``.
        """
        return ShowroomOpenAIAgentGraphBuilder().build(vector_store_ids)

