"""Map OpenAI Agents ``Runner.run`` results to ``ShowroomResponse``."""

from __future__ import annotations

import json
import logging
from typing import Any, ClassVar

from showroom.domain.schemas import ShowroomResponse

logger = logging.getLogger(__name__)


class ShowroomAgentStateExtractor:
    """
    Normalizes OpenAI Agents ``Runner.run`` output into the ``ShowroomResponse`` contract.
    """

    __slots__ = ()

    _default: ClassVar[ShowroomAgentStateExtractor | None] = None

    @classmethod
    def default(cls) -> ShowroomAgentStateExtractor:
        """Process-wide singleton for presentation layers that do not inject extractors."""
        if cls._default is None:
            cls._default = cls()
        return cls._default

    def from_run_result(self, result: Any, session_id: str) -> ShowroomResponse:
        """Build ``ShowroomResponse`` from OpenAI Agents ``RunResult`` output."""
        output = getattr(result, "final_output", None)
        if isinstance(output, ShowroomResponse):
            return output
        if isinstance(output, dict):
            try:
                return ShowroomResponse(**output)
            except Exception:
                logger.exception("Invalid final_output dict session_id=%s", session_id)
        if isinstance(output, str):
            try:
                return ShowroomResponse(**json.loads(output))
            except Exception:
                logger.exception("Failed to parse JSON final_output session_id=%s", session_id)
                return ShowroomResponse(
                    message_agent=output,
                    channel="text",
                    intent="unknown",
                    session_id=session_id,
                )

        return self._fallback(session_id)

    def _fallback(self, session_id: str) -> ShowroomResponse:
        return ShowroomResponse(
            message_agent="I'm here to help. How can I assist you today?",
            channel="text",
            intent="unknown",
            session_id=session_id,
        )

    from_agent_state = from_run_result
