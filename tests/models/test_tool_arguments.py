from vera.models.tool_arguments import INVALID_TOOL_ARGUMENTS, decode_tool_arguments


def test_decode_accepts_object_string() -> None:
    arguments, error = decode_tool_arguments('{"path":"a.py"}')
    assert arguments == {"path": "a.py"}
    assert error is None


def test_decode_accepts_mapping() -> None:
    arguments, error = decode_tool_arguments({"path": "a.py"})
    assert arguments == {"path": "a.py"}
    assert error is None


def test_decode_marks_truncated_json() -> None:
    arguments, error = decode_tool_arguments('{"summary":"fifth page","changes":[')
    assert arguments == {}
    assert error == INVALID_TOOL_ARGUMENTS


def test_decode_marks_non_object_json() -> None:
    arguments, error = decode_tool_arguments("[1]")
    assert arguments == {}
    assert error == INVALID_TOOL_ARGUMENTS
