from pathlib import Path

from tests.session.controller_helpers import (
    make_controller,
    proposal,
)
from vera.contracts.events import EventEnvelope
from vera.session.actions import (
    ConfirmExternalEditor,
    ExecuteSlashCommand,
    OpenExternalEditor,
    ResolveSessionApproval,
    SubmitPrompt,
)


def test_external_editor_requires_preview_then_returns_text(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = make_controller(workspace, [], editor_argv=("/usr/bin/true",))
    preview = tuple(controller.dispatch(OpenExternalEditor(text="draft")))
    assert preview[-1].type == "session.editor_preview"
    assert preview[-1].payload["needs_confirmation"] is True
    tuple(controller.dispatch(ConfirmExternalEditor(accept=True)))
    closed = tuple(controller.dispatch(OpenExternalEditor(text="draft")))
    assert closed[-1].type == "session.editor_closed"
    assert closed[-1].payload["status"] == "unchanged"


def test_external_editor_rejects_unconfigured_argv(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = make_controller(workspace, [])
    outputs = tuple(controller.dispatch(OpenExternalEditor(text="draft")))
    assert outputs[-1].payload["reason_code"] == "editor_unconfigured"


def test_new_slash_commands_are_structured_and_unknown_is_not_executed(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = make_controller(workspace, [])
    help_event = tuple(controller.dispatch(ExecuteSlashCommand(raw="/help")))[-1]
    assert help_event.type == "session.help"
    assert "代码与证据" in str(help_event.payload["text"])
    unknown = tuple(controller.dispatch(ExecuteSlashCommand(raw="/docotr")))[-1]
    assert unknown.type == "session.message"
    assert "/doctor" in str(unknown.payload.get("suggestions"))
    doctor = tuple(controller.dispatch(ExecuteSlashCommand(raw="/doctor")))[-1]
    assert doctor.type == "session.doctor"
    usage = tuple(controller.dispatch(ExecuteSlashCommand(raw="/usage")))[-1]
    assert usage.payload["calls"] == "unavailable"
    theme = tuple(controller.dispatch(ExecuteSlashCommand(raw="/theme high-contrast")))[-1]
    assert theme.payload["theme"] == "high-contrast"
    assert "当前主题：high-contrast" in str(theme.payload["text"])
    listed = tuple(controller.dispatch(ExecuteSlashCommand(raw="/theme")))[-1]
    assert listed.payload["theme"] == "high-contrast"
    unknown_theme = tuple(controller.dispatch(ExecuteSlashCommand(raw="/theme neon")))[-1]
    assert unknown_theme.type == "session.message"
    assert "未知主题" in str(unknown_theme.payload["text"])
    diff = tuple(controller.dispatch(ExecuteSlashCommand(raw="/diff")))[-1]
    assert diff.type == "session.diff"
    assert diff.payload["files"] == []
    review = tuple(controller.dispatch(ExecuteSlashCommand(raw="/review")))[-1]
    assert review.type == "session.review"


def test_diff_after_completed_run_uses_last_changeset(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    controller = make_controller(workspace, [proposal("c1", "new\n")])
    started = tuple(controller.dispatch(SubmitPrompt(text="edit hello")))
    pending = next(
        item
        for item in started
        if isinstance(item, EventEnvelope) and item.type == "approval.required"
    )
    tuple(
        controller.dispatch(
            ResolveSessionApproval(
                approval_id=str(pending.payload["approval_id"]),
                decision="approve",
            )
        )
    )
    assert controller.active_run_id is None
    diff = tuple(controller.dispatch(ExecuteSlashCommand(raw="/diff")))[-1]
    assert diff.type == "session.diff"
    files = diff.payload["files"]
    assert isinstance(files, list) and files
    assert files[0]["path"] == "hello.txt"
    text = str(diff.payload.get("text", ""))
    assert "hello.txt" in text
    assert "没有 Diff。" not in text
    assert diff.payload.get("applied") is True
    assert "未写入工作区" not in text


def test_diff_before_apply_is_labeled_unwritten(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    controller = make_controller(workspace, [proposal("c1", "new\n")])
    tuple(controller.dispatch(SubmitPrompt(text="edit hello")))
    diff = tuple(controller.dispatch(ExecuteSlashCommand(raw="/diff")))[-1]
    assert diff.type == "session.diff"
    assert diff.payload.get("applied") is False
    assert "未写入工作区" in str(diff.payload.get("text", ""))
    assert (workspace / "hello.txt").read_text(encoding="utf-8") == "old\n"
