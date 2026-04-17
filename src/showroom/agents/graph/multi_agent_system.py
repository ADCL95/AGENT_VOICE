"""Build the OpenAI Agents SDK graph: orchestrator + specialist handoff agents."""

from __future__ import annotations

from typing import Any

from agents import Agent
from showroom.agents.definitions import (
    ESCALATION_AGENT_NAME,
    ORCHESTRATOR_AGENT_NAME,
    PRODUCT_INFO_AGENT_NAME,
    PURCHASE_INTENT_AGENT_NAME,
    SPACE_ANALYSIS_AGENT_NAME,
)
from showroom.agents.prompts import (
    ESCALATION_AGENT_PROMPT,
    ORCHESTRATOR_PROMPT,
    PRODUCT_AGENT_PROMPT,
    PURCHASE_AGENT_PROMPT,
    SPACE_AGENT_PROMPT,
)
from showroom.agents.tools.rag_search import ShowroomVectorStoreToolSet
from showroom.core.settings import get_settings
from showroom.domain.schemas import ShowroomResponse


class ShowroomOpenAIAgentGraphBuilder:
    """
    Builds the OpenAI Agents SDK graph using handoffs for specialist delegation.
    """

    __slots__ = ()

    def build(self, vector_store_ids: list[str]) -> Any:
        """Return the orchestrator ``Agent`` ready for ``Runner.run``."""
        settings = get_settings()
        toolset = ShowroomVectorStoreToolSet(
            vector_store_ids=vector_store_ids,
            max_results=settings.rag_max_results,
        )

        product_agent = Agent(
            name=PRODUCT_INFO_AGENT_NAME,
            instructions=PRODUCT_AGENT_PROMPT,
            tools=toolset.build_product_tools(),
            output_type=ShowroomResponse,
            model=settings.model_main,
        )
        space_agent = Agent(
            name=SPACE_ANALYSIS_AGENT_NAME,
            instructions=SPACE_AGENT_PROMPT,
            tools=toolset.build_space_tools(),
            output_type=ShowroomResponse,
            model=settings.model_main,
        )
        purchase_agent = Agent(
            name=PURCHASE_INTENT_AGENT_NAME,
            instructions=PURCHASE_AGENT_PROMPT,
            tools=toolset.build_purchase_tools(),
            output_type=ShowroomResponse,
            model=settings.model_main,
        )
        escalation_agent = Agent(
            name=ESCALATION_AGENT_NAME,
            instructions=ESCALATION_AGENT_PROMPT,
            output_type=ShowroomResponse,
            model=settings.model_main,
        )

        return Agent(
            name=ORCHESTRATOR_AGENT_NAME,
            instructions=ORCHESTRATOR_PROMPT,
            handoffs=[
                product_agent,
                space_agent,
                purchase_agent,
                escalation_agent,
            ],
            model=settings.model_main,
        )
