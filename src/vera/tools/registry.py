"""Typed registry and dispatch for Core tools."""

from typing import Any, Protocol

from vera.contracts.tool_actions import ToolEffect
from vera.tools.definitions import ToolDefinitionV2, ToolResult


class DuplicateToolError(ValueError):
    """Raised when a tool name is registered more than once."""


class Tool(Protocol):
    name: str
    input_model: type[Any]
    definition: ToolDefinitionV2

    def execute(self, arguments: Any) -> Any: ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise DuplicateToolError(tool.name)
        self._tools[tool.name] = tool

    def definitions(self) -> tuple[ToolDefinitionV2, ...]:
        """Return versioned declarations; this method never executes a tool."""

        return tuple(self._definition_for(self._tools[name]) for name in sorted(self._tools))

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def implementation(self, name: str) -> Tool | None:
        """Locate an implementation for ToolExecutor without dispatching it."""

        return self._tools.get(name)

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, error_code="unknown_tool")
        parsed = tool.input_model.model_validate(arguments)
        result = tool.execute(parsed)
        return result if isinstance(result, ToolResult) else ToolResult.model_validate(result)

    @staticmethod
    def _definition_for(tool: Tool) -> ToolDefinitionV2:
        declared = getattr(tool, "definition", None)
        if isinstance(declared, ToolDefinitionV2):
            return declared
        # Compatibility-only fallback for historical Journals and test fixtures.
        return ToolDefinitionV2(
            name=tool.name,
            description=getattr(tool, "description", tool.name),
            input_schema=tool.input_model.model_json_schema(),
            tool_version=1,
            effects=(ToolEffect.WORKSPACE_READ,),
            supports_cancellation=False,
            supports_recovery=False,
            max_output_bytes=100_000,
        )
