from pathlib import Path

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.session.actions import ExecuteSlashCommand, ResolveSessionApproval, SubmitPrompt
from vera.session.command_catalog import CommandCatalog
from vera.session.controller import SessionController, SessionSnapshot
from vera.tools.registry import ToolRegistry


def make_controller(workspace: Path, turns: list[ModelTurn] | None = None) -> SessionController:
    state_dir = workspace.parent / "state"
    config = VeraConfig(
        state_dir=state_dir,
        limits=Limits(max_conversation_bytes=200_000),
        providers={
            "fake": ProviderConfig(
                base_url="https://example.invalid",
                model="fake-model",
                api_key_env="FAKE_API_KEY",
            )
        },
    )
    runtime = VeraRuntime(FakeModelAdapter(turns or []), ToolRegistry(), state_dir)
    deps = RuntimeDependencies(
        runtime=runtime,
        config=config,
        project_instructions=runtime.project_instructions,
    )
    return SessionController(deps, workspace, "fake")


def test_instructions_catalog_is_readonly_without_args() -> None:
    catalog = CommandCatalog()
    item = catalog.get("/instructions")
    assert item is not None
    assert item.name == "/instructions"
    assert item.usage == "/instructions"
    assert item.args == "none"
    assert "项目指令" in item.description
    parsed = catalog.parse(["/instructions", "extra"])
    snapshot = SessionSnapshot(
        session_id="s1",
        active_run_id=None,
        pending_approval_id=None,
        model_profile="fake",
        closed=False,
    )
    controller = None
    del snapshot, controller
    assert parsed.args == ("extra",)


def test_instructions_before_and_after_run(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("agents-body\n", encoding="utf-8")
    controller = make_controller(
        workspace,
        [ModelTurn(assistant_text="收到。", finish_reason="stop")],
    )
    before = [item for item in controller.dispatch(ExecuteSlashCommand(raw="/instructions"))]
    status = next(item for item in before if item.type == "project.instructions.status")
    assert status.payload["not_found"] is False
    assert status.payload["pending_next_run"] is False
    assert "AGENTS.md" in str(status.payload["text"])
    assert "agents-body" not in str(status.payload)
    extra = [item for item in controller.dispatch(ExecuteSlashCommand(raw="/instructions extra"))]
    usage = next(item for item in extra if item.type == "session.message")
    assert "用法：/instructions" in str(usage.payload["text"])
    list(controller.dispatch(SubmitPrompt(text="分析项目")))
    (workspace / "AGENTS.md").write_text("changed-after-run\n", encoding="utf-8")
    after = [item for item in controller.dispatch(ExecuteSlashCommand(raw="/instructions"))]
    later = next(item for item in after if item.type == "project.instructions.status")
    assert later.payload["pending_next_run"] is True
    assert "下个 Run 生效" in str(later.payload["text"])
    assert later.payload["run_guidance_hash"]
    assert "changed-after-run" not in str(later.payload)


def test_init_rejected_when_run_or_approval_active(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    from vera.models.base import ModelToolCall

    controller = make_controller(
        workspace,
        [
            ModelTurn(
                finish_reason="tool_calls",
                tool_calls=(
                    ModelToolCall(
                        call_id="1",
                        name="propose_changeset",
                        arguments={
                            "summary": "edit",
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
            )
        ],
    )
    outputs = list(controller.dispatch(SubmitPrompt(text="改文件")))
    assert any(item.type == "approval.required" for item in outputs)
    rejected = list(controller.dispatch(ExecuteSlashCommand(raw="/init")))
    assert rejected[0].type == "session.action_rejected"
    assert rejected[0].payload["reason_code"] == "approval_pending"
    list(
        controller.dispatch(
            ResolveSessionApproval(
                approval_id=str(outputs[-1].payload["approval_id"]),
                decision="reject",
            )
        )
    )
    idle = make_controller(workspace, [])
    idle.mark_active("run_busy")
    busy = list(idle.dispatch(ExecuteSlashCommand(raw="/init")))
    assert busy[0].payload["reason_code"] == "run_active"
