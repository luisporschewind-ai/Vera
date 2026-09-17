from pathlib import Path

from pydantic import BaseModel

from vera.contracts.commands import StartRun
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime, claims_unissued_changeset
from vera.tools.definitions import ToolResult
from vera.tools.filesystem import read_file
from vera.tools.registry import ToolRegistry
from vera.workspace.paths import WorkspacePaths


class ReadInput(BaseModel):
    path: str


class ReadTool:
    name = "read_file"
    description = "read a UTF-8 file"
    input_model = ReadInput

    def __init__(self, root: Path) -> None:
        self.paths = WorkspacePaths(root)

    def execute(self, arguments: ReadInput) -> ToolResult:
        return read_file(self.paths, arguments.path)


def test_plain_assistant_text_completes_without_changes(tmp_path: Path) -> None:
    adapter = FakeModelAdapter(
        [ModelTurn(assistant_text="你好，我是 Vera。", finish_reason="stop")]
    )
    runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / "state")

    events = list(
        runtime.handle(StartRun(goal="Hello", workspace_root=tmp_path, model_profile="fake"))
    )

    assert [event.type for event in events][-2:] == [
        "assistant.message",
        "run.completed",
    ]
    assert events[-2].payload["content"] == "你好，我是 Vera。"
    assert events[-1].payload == {"state": "completed", "outcome": "responded"}
    assert not any(
        event.type in {"changeset.proposed", "approval.required", "checkpoint.created"}
        for event in events
    )


def test_empty_model_response_fails_explicitly(tmp_path: Path) -> None:
    adapter = FakeModelAdapter([ModelTurn(assistant_text="", finish_reason="stop")])
    runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / "state")

    events = list(
        runtime.handle(StartRun(goal="Hello", workspace_root=tmp_path, model_profile="fake"))
    )

    assert events[-1].type == "run.failed"
    assert events[-1].payload["reason"] == "empty_model_response"


def test_empty_after_tools_nudges_then_completes(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("entry\n", encoding="utf-8")
    adapter = FakeModelAdapter(
        [
            ModelTurn(
                finish_reason="tool_calls",
                reasoning_content="先读文件",
                tool_calls=(
                    ModelToolCall(call_id="1", name="read_file", arguments={"path": "hello.txt"}),
                ),
            ),
            ModelTurn(assistant_text="", finish_reason="stop", reasoning_content="整理调查结果"),
            ModelTurn(assistant_text="入口在 hello.txt。", finish_reason="stop"),
        ]
    )
    registry = ToolRegistry()
    registry.register(ReadTool(tmp_path))
    runtime = VeraRuntime(adapter, registry, tmp_path / "state")

    events = list(
        runtime.handle(StartRun(goal="入口在哪？", workspace_root=tmp_path, model_profile="fake"))
    )

    assert events[-2].type == "assistant.message"
    assert events[-2].payload["content"] == "入口在 hello.txt。"
    assert events[-1].payload == {"state": "completed", "outcome": "responded"}
    assert any(
        "不要返回空响应" in message.content
        for request in adapter.requests
        for message in request.messages
        if message.role == "user"
    )


def test_empty_after_tools_still_fails_if_nudge_returns_empty(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("entry\n", encoding="utf-8")
    adapter = FakeModelAdapter(
        [
            ModelTurn(
                finish_reason="tool_calls",
                tool_calls=(
                    ModelToolCall(call_id="1", name="read_file", arguments={"path": "hello.txt"}),
                ),
            ),
            ModelTurn(assistant_text="", finish_reason="stop"),
            ModelTurn(assistant_text="", finish_reason="stop"),
        ]
    )
    registry = ToolRegistry()
    registry.register(ReadTool(tmp_path))
    runtime = VeraRuntime(adapter, registry, tmp_path / "state")

    events = list(
        runtime.handle(StartRun(goal="入口在哪？", workspace_root=tmp_path, model_profile="fake"))
    )

    assert events[-1].type == "run.failed"
    assert events[-1].payload["reason"] == "empty_model_response"


def test_readonly_tool_then_text_completes_without_changes(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("entry\n", encoding="utf-8")
    adapter = FakeModelAdapter(
        [
            ModelTurn(
                finish_reason="tool_calls",
                tool_calls=(
                    ModelToolCall(call_id="1", name="read_file", arguments={"path": "hello.txt"}),
                ),
            ),
            ModelTurn(assistant_text="入口在 hello.txt。", finish_reason="stop"),
        ]
    )
    registry = ToolRegistry()
    registry.register(ReadTool(tmp_path))
    runtime = VeraRuntime(adapter, registry, tmp_path / "state")

    events = list(
        runtime.handle(StartRun(goal="入口在哪？", workspace_root=tmp_path, model_profile="fake"))
    )

    assert events[-2].type == "assistant.message"
    assert events[-2].payload["content"] == "入口在 hello.txt。"
    assert events[-1].payload == {"state": "completed", "outcome": "responded"}
    assert not any(
        event.type in {"changeset.proposed", "approval.required", "checkpoint.created"}
        for event in events
    )
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "entry\n"


def test_claims_unissued_changeset_markers() -> None:
    assert claims_unissued_changeset("以下修改已形成 Change Set，等待你审批。")
    assert claims_unissued_changeset("关键取舍等待审批。")
    assert not claims_unissued_changeset("入口在 hello.txt。")
    assert not claims_unissued_changeset("若你同意这些取舍，我会调用 propose_changeset。")


def test_claimed_changeset_text_nudges_then_proposes(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    adapter = FakeModelAdapter(
        [
            ModelTurn(
                assistant_text="以下修改已形成 Change Set，等待你审批。",
                finish_reason="stop",
            ),
            ModelTurn(
                finish_reason="tool_calls",
                tool_calls=(
                    ModelToolCall(
                        call_id="1",
                        name="propose_changeset",
                        arguments={
                            "summary": "add stats",
                            "changes": [
                                {
                                    "operation": "update",
                                    "path": "hello.txt",
                                    "after_content": "new\n",
                                }
                            ],
                        },
                    ),
                ),
            ),
        ]
    )
    runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / "state")
    events = list(
        runtime.handle(StartRun(goal="改文件", workspace_root=tmp_path, model_profile="fake"))
    )
    assert any(event.type == "approval.required" for event in events)
    assert not any(event.type == "run.completed" for event in events)
    assert any(
        "只有该工具才会出现审批卡" in message.content
        for request in adapter.requests
        for message in request.messages
        if message.role == "user"
    )


def test_claimed_changeset_nudge_then_honest_text(tmp_path: Path) -> None:
    adapter = FakeModelAdapter(
        [
            ModelTurn(
                assistant_text="以下修改已形成 Change Set，等待你审批。",
                finish_reason="stop",
            ),
            ModelTurn(assistant_text="目前还没有提出变更。", finish_reason="stop"),
        ]
    )
    runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / "state")
    events = list(
        runtime.handle(StartRun(goal="改文件", workspace_root=tmp_path, model_profile="fake"))
    )
    assert events[-2].type == "assistant.message"
    assert events[-2].payload["content"] == "目前还没有提出变更。"
    assert events[-1].payload == {"state": "completed", "outcome": "responded"}
    assert not any(event.type == "approval.required" for event in events)


def test_claimed_changeset_nudge_only_once(tmp_path: Path) -> None:
    claim = "已形成 Change Set，等待你审批。"
    adapter = FakeModelAdapter(
        [
            ModelTurn(assistant_text=claim, finish_reason="stop"),
            ModelTurn(assistant_text=claim, finish_reason="stop"),
        ]
    )
    runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / "state")
    events = list(
        runtime.handle(StartRun(goal="改文件", workspace_root=tmp_path, model_profile="fake"))
    )
    assert events[-2].payload["content"] == claim
    assert events[-1].payload == {"state": "completed", "outcome": "responded"}
    nudge_count = sum(
        1
        for request in adapter.requests
        for message in request.messages
        if message.role == "user" and "只有该工具才会出现审批卡" in message.content
    )
    assert nudge_count == 1
