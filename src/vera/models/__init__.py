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


def __getattr__(name: str) -> object:
    if name == "OpenAICompatibleAdapter":
        from vera.models.openai_compatible import OpenAICompatibleAdapter

        return OpenAICompatibleAdapter
    raise AttributeError(name)
