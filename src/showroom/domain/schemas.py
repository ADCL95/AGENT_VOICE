"""
Pydantic response contract for the Aether Motors AI Showroom.

Every agent MUST return a ShowroomResponse regardless of intent.
The 3D frontend uses the `channel` field to decide how to render the output.
"""

from typing import Literal

from pydantic import BaseModel, Field


class ShowroomResponse(BaseModel):
    """
    Universal response contract — all agents output this schema.

    channel behaviour:
      - "text"       → chat overlay in the 3D frontend
      - "voice"      → play AI-generated speech (OpenAI Speech API / TTS) from ``message_agent``
      - "escalation" → triggers human-handoff notification in the frontend
    """

    message_agent: str = Field(
        description="The text shown or spoken to the user. Always in first person, always helpful."
    )
    channel: Literal["text", "voice", "escalation"] = Field(
        description='Output channel: "text" for chat, "voice" for TTS playback of message_agent, "escalation" for handoff.'
    )
    intent: str = Field(
        description="The classified intent for this conversation turn."
    )
    session_id: str = Field(
        description="Session identifier — passed through unchanged from the request."
    )
