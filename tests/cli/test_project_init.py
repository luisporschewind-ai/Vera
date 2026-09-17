from pathlib import Path

from typer.testing import CliRunner

from tests.cli.fakes import make_changeset_runtime
from vera.bootstrap import RuntimeDependencies
from vera.cli import app
from vera.cli_driver import drive_run
from vera.config import Limits, VeraConfig
from vera.contracts.commands import StartRun
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.presentation.sanitize import sanitize_terminal_text
from vera.runtime.engine import VeraRuntime
from vera.runtime.prompts import PROJECT_INIT_GOAL
from vera.tools.registry import ToolRegistry


def _deps(workspace: Path, turns: list[ModelTurn]) -> RuntimeDependencies:
    state_dir = workspace.parent / "state"
    runtime = VeraRuntime(FakeModelAdapter(turns), ToolRegistry(), state_dir)
    return RuntimeDependencies(
        runtime=runtime,
        config=VeraConfig(state_dir=state_dir, limits=Limits(), providers={}),
        project_instructions=runtime.project_instructions,
    )


def _manifest(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_init_help_mentions_vera_md_approval() -> None:
    result = CliRunner().invoke(app, ["init", "--help"])
    assert result.exit_code == 0
    text = sanitize_terminal_text(result.stdout)
    assert "只提议 VERA.md，批准后写入" in text


def test_json_init_cancels_without_writing(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("agents\n", encoding="utf-8")
    before = _manifest(workspace)
    deps = _deps(
        workspace,
        [
            ModelTurn(
                finish_reason="tool_calls",
                tool_calls=(
                    ModelToolCall(
                        call_id="1",
                        name="propose_changeset",
                        arguments={
                            "summary": "create vera",
                            "changes": [
                                {
                                    "operation": "create",
                                    "path": "VERA.md",
                                    "after_content": "# Project guidance for Vera\n",
                                }
                            ],
                        },
                    ),
                ),
            )
        ],
    )
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_args, **_kwargs: deps)
    result = CliRunner().invoke(app, ["init", "--workspace", str(workspace), "--json"])
    assert result.exit_code == 2
    assert '"type":"run.cancelled"' in result.stdout
    assert "agents\n" not in result.stdout.replace("AGENTS.md", "")
    assert _manifest(workspace) == before


def test_init_reject_keeps_bytes_and_approve_updates_vera(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sentinel = "KEEP-THIS-PARAGRAPH\n"
    (workspace / "VERA.md").write_text(sentinel + "old\n", encoding="utf-8")
    turns = [
        ModelTurn(
            finish_reason="tool_calls",
            tool_calls=(
                ModelToolCall(
                    call_id="1",
                    name="propose_changeset",
                    arguments={
                        "summary": "update vera",
                        "changes": [
                            {
                                "operation": "update",
                                "path": "VERA.md",
                                "after_content": sentinel + "new\n",
                            }
                        ],
                    },
                ),
            ),
        )
    ]
    reject_runtime = _deps(workspace, turns).runtime
    rejected = drive_run(
        reject_runtime,
        StartRun(
            goal=PROJECT_INIT_GOAL,
            workspace_root=workspace,
            model_profile="fake",
            mode="project_init",
        ),
        lambda _event: "reject",
        lambda _batch: None,
    )
    assert (workspace / "VERA.md").read_text(encoding="utf-8") == sentinel + "old\n"
    assert any(event.type == "approval.resolved" for event in rejected)
    approve_runtime = _deps(workspace, turns).runtime
    approved = drive_run(
        approve_runtime,
        StartRun(
            goal=PROJECT_INIT_GOAL,
            workspace_root=workspace,
            model_profile="fake",
            mode="project_init",
        ),
        lambda _event: "approve",
        lambda _batch: None,
    )
    assert approved[-1].type == "run.completed"
    updated = (workspace / "VERA.md").read_text(encoding="utf-8")
    assert updated.startswith(sentinel)
    assert "new\n" in updated
    assert updated.count(sentinel) == 1


def test_help_lists_init_command() -> None:
    result = CliRunner().invoke(app, ["--help"])
    text = sanitize_terminal_text(result.stdout)
    assert "init" in text


def test_init_without_provider_does_not_write(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = CliRunner().invoke(app, ["init", "--workspace", str(workspace)])
    combined = result.stdout + result.stderr
    assert result.exit_code == 5
    assert "missing_provider_config" in combined
    assert not (workspace / "VERA.md").exists()


def test_regular_changeset_runtime_still_available(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    runtime = make_changeset_runtime(workspace, tmp_path / "state")
    assert runtime is not None
