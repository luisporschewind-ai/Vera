"""Declared model provider capabilities."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_calling: bool = True
    parallel_tool_calls: bool = False
    context_tokens: int | None = Field(default=None, ge=1)
    usage: bool = True
    request_id: bool = True
    streaming: bool = False

    reasoning: Literal["unavailable", "provider_default"] = "unavailable"

    def supports_request(self, *, has_tools: bool) -> bool:
        return not (has_tools and not self.tool_calling)
