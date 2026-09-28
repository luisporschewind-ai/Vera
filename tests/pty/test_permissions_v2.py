import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from tests.pty.harness import PtyHarness
from vera.cli_session_presenter import SessionPresenter
from vera.contracts.events import EventEnvelope
from vera.presentation.projector import AppendBlock, TimelineProjector
from vera.session.models import PermissionStatus
from vera.session.protocol import SessionRecordCodec


def _approval_event() -> EventEnvelope:
    return EventEnvelope(
        event_id="approval_event_1",
        run_id="run_1",
        sequence=1,
        timestamp=datetime.now(UTC),
        type="approval.required",
        payload={
            "approval_id": "approval_1",
            "kind": "tool",
            "risk": "high",
            "argv": ["printf", "safe"],
            "cwd": "/workspace",
            "effect": "执行命令",
            "available_scopes": ["once", "run"],
        },
    )


def test_tui_plain_and_json_share_core_approval_facts() -> None:
    event = _approval_event()

    mutations = TimelineProjector().apply(event)
    assert isinstance(mutations[0], AppendBlock)
    body = mutations[0].block.body
    assert "风险：高" in body
    assert "授权范围：once, run" in body
    assert "工作目录：/workspace" in body
    assert "授权范围：once, run, workspace" not in body
    assert "执行命令" in body

    payload = json.loads(SessionRecordCodec.encode(SessionRecordCodec.from_output(event)))
    assert payload["event"]["payload"]["available_scopes"] == ["once", "run"]
    assert payload["event"]["payload"]["cwd"] == "/workspace"


def test_plain_permission_status_uses_structured_scope_summary() -> None:
    output: list[str] = []
    SessionPresenter(output.append).write_permissions(
        PermissionStatus(
            approval_mode="manual",
            changeset_approval="required",
            command_policy="allow/deny/approval-required",
            user_allowed_prefixes=(),
            execution_boundary="current user",
            os_sandbox=False,
            trusted=True,
            approval_scopes=("once", "run", "workspace"),
        )
    )
    text = "\n".join(output)
    assert "Workspace trust   trusted" in text
    assert "Approval scopes   once, run, workspace" in text


def test_pty_plain_permissions_exposes_trust_without_tui_sequences(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    state_dir = tmp_path / "state"
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "TERM": "xterm-256color",
        "COLUMNS": "60",
        "LINES": "16",
        "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
        "VERA_PROVIDER_ENV_FILE": str(tmp_path / "missing.env"),
        "VERA_STATE_DIR": str(state_dir),
        "DEEPSEEK_API_KEY": "test-only-placeholder",
        "VERA_DEEPSEEK_BASE_URL": "https://example.invalid",
        "VERA_DEEPSEEK_MODEL": "test-model",
    }
    result = PtyHarness().spawn_and_run(
        [
            sys.executable,
            "-c",
            "from vera.cli import app; app()",
            "--plain",
            "--workspace",
            str(workspace),
        ],
        env=env,
        input_text="/permissions trust\n/permissions\n/exit\n",
        timeout=8.0,
    )
    assert result.exit_code == 0
    assert "Workspace trust   trusted" in result.output
    assert "Approval scopes   once, run, workspace" in result.output
    assert "\x1b[?1049h" not in result.output
