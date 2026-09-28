from pathlib import Path

import pytest

from vera.cli_presenter import HumanPresenter
from vera.contracts.commands import ResolveApproval, StartRun
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.process.supervisor import ProcessResult
from vera.runtime.engine import VeraRuntime
from vera.sandbox.access import AccessSession
from vera.sandbox.apple_services import APPLE_IOS_BUILD_SERVICES
from vera.sandbox.apple_volume import APPLE_BUILD_STORAGE
from vera.sandbox.files import PermissionPaths
from vera.sandbox.tools import RequestFileAccessTool
from vera.tools.bash import BashTool
from vera.tools.file_mutation import EditTool, WriteTool
from vera.tools.registry import ToolRegistry


@pytest.mark.parametrize("directory", [False, True])
def test_plain_file_approval_discloses_core_scope_before_grant(tmp_path: Path, directory: bool):
    work = tmp_path / "work"
    work.mkdir()
    outside = tmp_path / "outside"
    if directory:
        outside.mkdir()
    else:
        outside.write_text("fake")
    session = AccessSession(work)
    registry = ToolRegistry()
    registry.register(RequestFileAccessTool(session, registry))
    runtime = VeraRuntime(
        FakeModelAdapter(
            [
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(
                        ModelToolCall(
                            call_id="request",
                            name="request_file_access",
                            arguments={
                                "path": str(outside),
                                "mode": "read_write" if directory else "read",
                                "scope": "session",
                                "reason": "验证单文件授权边界",
                            },
                        ),
                    ),
                )
            ]
        ),
        registry,
        tmp_path / "state",
        access_session=session,
    )
    events = list(
        runtime.handle(StartRun(goal="请求授权", workspace_root=work, model_profile="fake"))
    )
    approval = next(item for item in events if item.type == "approval.required")
    assert not session.grants()
    lines = []
    presenter = HumanPresenter(lines.append)
    presenter.write_events((approval,))
    text = "\n".join(lines)
    assert str(outside.resolve()) in text
    assert ("读写" if directory else "只读") in text
    assert ("包含子目录" if directory else "仅此文件") in text
    assert "本次会话" in text
    assert "验证单文件授权边界" in text
    assert "Change Set" not in text
    assert "文件访问授权" in presenter.approval_prompt(approval)


def test_plain_bash_approval_discloses_actual_command_before_execution(tmp_path: Path):
    registry = ToolRegistry()
    registry.register(BashTool(tmp_path))
    runtime = VeraRuntime(
        FakeModelAdapter(
            [
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(
                        ModelToolCall(
                            call_id="command",
                            name="bash",
                            arguments={
                                "argv": ["/bin/cp", "inside.txt", "copy.txt"],
                                "cwd": ".",
                                "timeout_seconds": 5,
                            },
                        ),
                    ),
                )
            ]
        ),
        registry,
        tmp_path / "state",
    )
    events = list(
        runtime.handle(StartRun(goal="复制", workspace_root=tmp_path, model_profile="fake"))
    )
    approval = next(item for item in events if item.type == "approval.required")
    lines = []
    presenter = HumanPresenter(lines.append)
    presenter.write_events((approval,))
    text = "\n".join(lines)
    assert "/bin/cp inside.txt copy.txt" in text
    assert "工作目录：." in text
    assert "5" in text
    assert "Change Set" not in text
    assert "命令" in presenter.approval_prompt(approval)


def test_generic_ios_build_approval_discloses_once_only_system_services(tmp_path: Path):
    registry = ToolRegistry()
    registry.register(BashTool(tmp_path))
    runtime = VeraRuntime(
        FakeModelAdapter(
            [
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(
                        ModelToolCall(
                            call_id="ios-build",
                            name="bash",
                            arguments={
                                "argv": [
                                    "/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild",
                                    "-project",
                                    "Fake.xcodeproj",
                                    "-scheme",
                                    "Fake",
                                    "-sdk",
                                    "iphoneos",
                                    "-destination",
                                    "generic/platform=iOS",
                                    "CODE_SIGNING_ALLOWED=NO",
                                    "CODE_SIGNING_REQUIRED=NO",
                                    "CODE_SIGN_IDENTITY=",
                                    "build",
                                ],
                                "cwd": ".",
                                "timeout_seconds": 120,
                            },
                        ),
                    ),
                )
            ]
        ),
        registry,
        tmp_path / "state",
    )

    events = list(
        runtime.handle(
            StartRun(goal="构建 iOS 假工程", workspace_root=tmp_path, model_profile="fake")
        )
    )
    approval = next(item for item in events if item.type == "approval.required")
    grant = approval.payload["system_service_grant"]
    assert approval.payload["available_scopes"] == ["once"]
    assert approval.payload["target_facts_hash"]
    assert grant["capability"] == "apple_ios_build_services"
    assert grant["services"] == list(APPLE_IOS_BUILD_SERVICES)
    assert "com.apple.CoreSimulator.SimLaunchHost-x86" in grant["services"]
    assert approval.payload["build_storage"] == APPLE_BUILD_STORAGE
    assert grant["inherited_by_descendants"] is True
    assert grant["may_access_current_user_simulator_state"] is True
    lines = []
    HumanPresenter(lines.append).write_events((approval,))
    rendered = "\n".join(lines)
    assert "com.apple.CoreSimulator.CoreSimulatorService" in rendered
    assert "后代" in rendered
    assert "模拟器状态" in rendered
    assert "-derivedDataPath" in rendered
    assert "8 GiB" in rendered


def test_approved_generic_ios_build_passes_ephemeral_service_capability(tmp_path: Path):
    class RecordingSupervisor:
        def __init__(self):
            self.requests = []

        def run(self, request, *, cancel_event=None):
            self.requests.append(request)
            return ProcessResult("exited", 0, b"BUILD SUCCEEDED", b"")

    supervisor = RecordingSupervisor()
    registry = ToolRegistry()
    registry.register(BashTool(tmp_path, supervisor=supervisor))
    runtime = VeraRuntime(
        FakeModelAdapter(
            [
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(
                        ModelToolCall(
                            call_id="approved-ios-build",
                            name="bash",
                            arguments={
                                "argv": [
                                    "/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild",
                                    "-project",
                                    "Fake.xcodeproj",
                                    "-scheme",
                                    "Fake",
                                    "-sdk",
                                    "iphoneos",
                                    "-destination",
                                    "generic/platform=iOS",
                                    "CODE_SIGNING_ALLOWED=NO",
                                    "CODE_SIGNING_REQUIRED=NO",
                                    "CODE_SIGN_IDENTITY=",
                                    "build",
                                ],
                                "cwd": ".",
                                "timeout_seconds": 120,
                            },
                        ),
                    ),
                ),
                ModelTurn(assistant_text="构建完成。", finish_reason="stop"),
            ]
        ),
        registry,
        tmp_path / "state",
    )
    events = list(
        runtime.handle(
            StartRun(goal="构建 iOS 假工程", workspace_root=tmp_path, model_profile="fake")
        )
    )
    approval = next(item for item in events if item.type == "approval.required")
    assert supervisor.requests == []

    list(
        runtime.handle(
            ResolveApproval(
                run_id=approval.payload["run_id"],
                approval_id=approval.payload["approval_id"],
                target_hash=approval.payload["target_hash"],
                decision="approve",
            )
        )
    )

    assert len(supervisor.requests) == 1
    assert supervisor.requests[0].apple_ios_build_services is True


@pytest.mark.parametrize("name", ["write", "edit"])
def test_external_mutation_approval_shows_path_and_diff_before_write(tmp_path: Path, name: str):
    work = tmp_path / "work"
    work.mkdir()
    target = tmp_path / "a.txt"
    target.write_text("BEFORE\n")
    session = AccessSession(work)
    request = session.request(target, "read_write", "session")
    session.resolve(request.request_id, approved=True)
    registry = ToolRegistry()
    registry.register(WriteTool(work, paths=PermissionPaths(session)))
    registry.register(EditTool(work, paths=PermissionPaths(session)))
    arguments = {"path": str(target)}
    arguments.update(
        {"content": "AFTER\n"}
        if name == "write"
        else {
            "old_text": "BEFORE",
            "new_text": "AFTER",
        }
    )
    runtime = VeraRuntime(
        FakeModelAdapter(
            [
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(ModelToolCall(call_id="mutation", name=name, arguments=arguments),),
                )
            ]
        ),
        registry,
        tmp_path / "state",
        access_session=session,
    )
    events = list(
        runtime.handle(StartRun(goal="修改假文件", workspace_root=work, model_profile="fake"))
    )
    approval = next(item for item in events if item.type == "approval.required")
    lines = []
    HumanPresenter(lines.append).write_events((approval,))
    text = "\n".join(lines)
    assert str(target) in text
    assert "-BEFORE" in text
    assert "+AFTER" in text
    assert target.read_text() == "BEFORE\n"
