"""Typed registry and dispatch for Core tools."""

from typing import Any, Protocol

from pydantic import BaseModel

from vera.tools.definitions import ToolResult


class DuplicateToolError(ValueError):
    """Raised when a tool name is registered more than once."""


class Tool(Protocol):
    name: str
    input_model: type[BaseModel]

    def execute(self, arguments: BaseModel) -> Any: ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise DuplicateToolError(tool.name)
        self._tools[tool.name] = tool

    def definitions(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, error_code="unknown_tool")
        parsed = tool.input_model.model_validate(arguments)
        result = tool.execute(parsed)
        return result if isinstance(result, ToolResult) else ToolResult.model_validate(result)
