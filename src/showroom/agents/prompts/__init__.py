"""
RISEN-style system prompts for the Aether Motors multi-agent harness.

RISEN methodology (per agent module):
  R — Role         : Who the agent IS and what gives it authority
  I — Instructions : How it thinks and behaves
  S — Steps        : The exact reasoning process to follow per request
  E — End Goal     : The precise output it must always produce
  N — Narrowing    : Hard constraints that cannot be violated

Structure mirrors the OpenAI Agents SDK graph: isolated specialist prompts under
``prompts/`` with a single orchestrator prompt for routing + handoff.
"""

from showroom.agents.prompts.escalation import ESCALATION_AGENT_PROMPT
from showroom.agents.prompts.orchestrator import ORCHESTRATOR_PROMPT
from showroom.agents.prompts.product import PRODUCT_AGENT_PROMPT
from showroom.agents.prompts.purchase import PURCHASE_AGENT_PROMPT
from showroom.agents.prompts.space import SPACE_AGENT_PROMPT

__all__ = [
    "ESCALATION_AGENT_PROMPT",
    "ORCHESTRATOR_PROMPT",
    "PRODUCT_AGENT_PROMPT",
    "PURCHASE_AGENT_PROMPT",
    "SPACE_AGENT_PROMPT",
]
