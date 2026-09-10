"""Provider-independent model contracts and adapters."""

from vera.models.base import (
    FakeModelAdapter,
    ModelAdapter,
    ModelMessage,
    ModelRequest,
    ModelToolCall,
    ModelTurn,
    ModelUsage,
)
from vera.models.openai_compatible import OpenAICompatibleAdapter

__all__ = [
    "FakeModelAdapter",
    "ModelAdapter",
    "ModelMessage",
    "ModelRequest",
    "ModelToolCall",
    "ModelTurn",
    "ModelUsage",
    "OpenAICompatibleAdapter",
]
