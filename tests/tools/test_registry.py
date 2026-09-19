from pydantic import BaseModel

from vera.tools.registry import DuplicateToolError, ToolRegistry


class EchoInput(BaseModel):
    value: str


class EchoTool:
    name = "echo"
    input_model = EchoInput

    def execute(self, arguments: EchoInput):
        return {"ok": True, "content": arguments.value}


def test_registry_rejects_unknown_tool() -> None:
    result = ToolRegistry().execute("missing", {})
    assert result.ok is False
    assert result.error_code == "unknown_tool"


def test_registry_validates_arguments_and_duplicate_names() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())
    assert registry.execute("echo", {"value": "ok"}).content == "ok"
    try:
        registry.execute("echo", {"value": 1})
    except Exception as exc:
        assert exc.__class__.__name__ == "ValidationError"
    else:
        raise AssertionError("invalid arguments must fail")
    try:
        registry.register(EchoTool())
    except DuplicateToolError:
        pass
    else:
        raise AssertionError("duplicate tool must fail")


def test_registry_definitions_are_versioned_and_do_not_dispatch() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())
    definitions = registry.definitions()
    assert [definition.name for definition in definitions] == ["echo"]
    assert definitions[0].schema_version == 2
