from pathlib import Path
from subprocess import CompletedProcess

import pytest

from vera.bootstrap import RuntimeDependencies
from vera.cli_session_presenter import SessionPresenter
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.contracts.events import EventEnvelope
from vera.models.base import FakeModelAdapter
from vera.runtime.engine import VeraRuntime
from vera.sandbox.access import AccessSession
from vera.sandbox.backend import SrtBackend
from vera.sandbox.settings import UnavailableBackend
from vera.sandbox.supervision import SandboxedSupervisor
from vera.session.actions import ExecuteSlashCommand
from vera.session.controller import SessionController
from vera.session.models import PermissionStatus
from vera.session.status import SessionStatusService
from vera.tools.registry import ToolRegistry


@pytest.mark.parametrize("configured", [False, True])
def test_permission_views_report_injected_boundary_without_claiming_os_probe(
    tmp_path: Path, configured: bool
) -> None:
    session = AccessSession(tmp_path)
    backend = (
        SrtBackend(runtime_root=tmp_path / "missing-runtime", base_readable=())
        if configured
        else UnavailableBackend()
    )
    runtime = VeraRuntime(
        FakeModelAdapter([]),
        ToolRegistry(),
        tmp_path / "state",
        access_session=session,
        process_supervisor=SandboxedSupervisor(session, backend),
    )
    config = VeraConfig(
        state_dir=tmp_path / "state",
        limits=Limits(),
        providers={
            "fake": ProviderConfig(
                base_url="https://example.invalid", model="fake", api_key_env="FAKE_API_KEY"
            )
        },
    )
    controller = SessionController(
        RuntimeDependencies(runtime=runtime, config=config), tmp_path, "fake"
    )

    class GitRunner:
        def run(self, argv, *, cwd, timeout):
            return CompletedProcess(argv, 128, "", "")

    controller.status_service = SessionStatusService(git_runner=GitRunner())
    outputs = tuple(controller.dispatch(ExecuteSlashCommand(raw="/permissions")))
    event = next(
        item
        for item in outputs
        if isinstance(item, EventEnvelope) and item.type == "session.permissions"
    )
    expected = "configured" if configured else "setup_required"
    assert event.payload.get("sandbox_state") == expected
    status = controller.session_status()
    assert status.permissions.sandbox_state == expected
    assert status.permissions.execution_boundary == "trusted Core; sandbox required for commands"
    assert status.permissions.network == "deny"

    lines: list[str] = []
    presenter = SessionPresenter(lines.append)
    presenter.write_permissions(PermissionStatus.model_validate(event.payload))
    presenter.write_status(status)
    text = "\n".join(lines)
    assert "no OS sandbox" not in text
    if configured:
        assert "已配置" in text
        assert "执行前检查" in text
        assert "已验证" not in text
    else:
        assert "未配置" in text
        assert "命令禁用" in text
