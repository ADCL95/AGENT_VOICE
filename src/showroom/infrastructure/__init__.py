"""External service adapters (OpenAI HTTP clients, etc.)."""

from showroom.infrastructure.openai_client import OpenAIProvider
from showroom.infrastructure.openai_realtime_sessions import (
    OpenAIRealtimeSessionsClient,
    VoiceWidgetEphemeralCredentialsIssuer,
)

__all__ = [
    "OpenAIProvider",
    "OpenAIRealtimeSessionsClient",
    "VoiceWidgetEphemeralCredentialsIssuer",
]
