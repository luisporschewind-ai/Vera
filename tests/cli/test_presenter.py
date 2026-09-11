from datetime import UTC, datetime

from vera.cli_presenter import HumanPresenter
from vera.contracts.events import EventEnvelope


def event(event_type: str, payload: dict, sequence: int = 1) -> EventEnvelope:
    return EventEnvelope(
        event_id=f"event-{sequence}",
        run_id="run-1",
        sequence=sequence,
        timestamp=datetime(2026, 9, 11, tzinfo=UTC),
        type=event_type,
        payload=payload,
    )


def test_presenter_displays_authoritative_diff_and_hash_before_approval() -> None:
    output: list[str] = []
    presenter = HumanPresenter(output.append)
    content_hash = "abc123"
    unified_diff = (
        "--- a/VeraTestDemo/ViewController.swift\n"
        "+++ b/VeraTestDemo/ViewController.swift\n"
        "@@ -1 +1 @@\n"
        "-view.backgroundColor = .blue\n"
        "+view.backgroundColor = .green\n"
    )

    presenter.write_events(
        (
            event(
                "changeset.proposed",
                {
                    "changeset_id": "changeset-1",
                    "content_hash": content_hash,
                    "files": [
                        {
                            "path": "VeraTestDemo/ViewController.swift",
                            "operation": "update",
                            "before_hash": "before",
                            "after_hash": "after",
                            "unified_diff": unified_diff,
                        }
                    ],
                },
            ),
        )
    )

    text = "\n".join(output)
    assert "VeraTestDemo/ViewController.swift" in text
    assert "-view.backgroundColor = .blue" in text
    assert "+view.backgroundColor = .green" in text
    assert content_hash in text


def test_presenter_displays_command_boundary_without_shell_execution() -> None:
    output: list[str] = []
    presenter = HumanPresenter(output.append)
    approval = event(
        "approval.required",
        {
            "approval_id": "approval-1",
            "kind": "command",
            "target_hash": "hash-1",
            "argv": ["python", "-m", "pytest", "tests/test app.py"],
            "cwd": ".",
            "risk": "medium",
        },
    )

    presenter.write_events((approval,))

    text = "\n".join(output)
    assert "python -m pytest 'tests/test app.py'" in text
    assert "工作目录：." in text
    assert "当前系统用户权限" in text
    assert presenter.approval_prompt(approval).startswith("批准这条验证命令")


def test_presenter_keeps_tool_output_compact_and_shows_terminal_state() -> None:
    output: list[str] = []
    presenter = HumanPresenter(output.append)

    presenter.write_events(
        (
            event(
                "tool.completed",
                {
                    "name": "read_file",
                    "ok": True,
                    "truncated": False,
                    "secret_file_contents": "must-not-be-rendered",
                },
            ),
            event("run.completed", {"state": "completed"}, sequence=2),
        )
    )

    text = "\n".join(output)
    assert "read_file：成功" in text
    assert "must-not-be-rendered" not in text
    assert "任务完成：run-1（completed）" in text


def test_presenter_displays_plain_assistant_message() -> None:
    output: list[str] = []
    presenter = HumanPresenter(output.append)

    presenter.write_events((event("assistant.message", {"content": "你好"}),))

    assert output == ["Vera：你好"]


def test_presenter_reports_compaction_without_reprinting_summary() -> None:
    output: list[str] = []
    presenter = HumanPresenter(output.append)
    summary = "很长的摘要内容" * 20

    presenter.write_events((event("conversation.compacted", {"summary": summary}),))

    text = "\n".join(output)
    assert "上下文已压缩" in text
    assert str(len(summary.encode("utf-8"))) in text
    assert summary not in text
