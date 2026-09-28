from pathlib import Path

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.contracts.events import EventEnvelope
from vera.contracts.tool_actions import ToolEffect
from vera.models.base import FakeModelAdapter
from vera.persistence.workspace_permissions import WorkspacePermissionStore
from vera.policy.permissions import PermissionGrant, WorkspacePermissionSnapshot
from vera.runtime.engine import VeraRuntime
from vera.session.actions import ExecuteSlashCommand
from vera.session.controller import SessionController
from vera.session.models import PermissionStatus
from vera.tools.registry import ToolRegistry


def test_permission_status_exposes_mode_trust_and_scopes() -> None:
    status = PermissionStatus(
        approval_mode="manual",
        changeset_approval="required",
        command_policy="allow/deny/approval-required",
        user_allowed_prefixes=(),
        execution_boundary="current user",
        os_sandbox=False,
        policy_mode="balanced",
        trusted=False,
    )
    assert status.policy_mode == "balanced"
    assert status.approval_scopes == ("once", "run", "workspace")


def test_permissions_trust_and_revoke_are_core_state_changes(tmp_path: Path) -> None:
    runtime = VeraRuntime(FakeModelAdapter([]), ToolRegistry(), tmp_path / "state")
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
    snapshot = runtime.policy_engine.snapshot
    runtime.workspace_permissions = WorkspacePermissionSnapshot(
        workspace_identity=snapshot.workspace_identity,
        policy_major_version=snapshot.builtin_policy_version,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=False,
    )
    output = tuple(controller.dispatch(ExecuteSlashCommand(raw="/permissions trust")))
    event = next(item for item in output if isinstance(item, EventEnvelope))
    assert event.type == "session.permissions"
    assert event.payload["trusted"] is True
    output = tuple(controller.dispatch(ExecuteSlashCommand(raw="/permissions revoke")))
    event = next(item for item in output if isinstance(item, EventEnvelope))
    assert event.payload["trusted"] is False

    permission_store = WorkspacePermissionStore(
        config.state_dir,
        policy_major_version=runtime.policy_engine.snapshot.builtin_policy_version,
        protected_roots_hash=runtime.policy_engine.snapshot.protected_roots_hash,
    )
    assert permission_store.load(snapshot.workspace_identity).trusted is False


def test_permissions_revoke_clears_existing_in_memory_grants(tmp_path: Path) -> None:
    runtime = VeraRuntime(FakeModelAdapter([]), ToolRegistry(), tmp_path / "state")
    config = VeraConfig(
        state_dir=tmp_path / "state",
        limits=Limits(),
        providers={
            "fake": ProviderConfig(
                base_url="https://example.invalid", model="fake", api_key_env="FAKE_API_KEY"
            )
        },
    )
    snapshot = runtime.policy_engine.snapshot
    runtime.workspace_permissions = WorkspacePermissionSnapshot(
        workspace_identity=snapshot.workspace_identity,
        policy_major_version=snapshot.builtin_policy_version,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=True,
        grants=(
            PermissionGrant(
                grant_id="grant_1",
                scope="workspace",
                tool_name="bash",
                effects=(ToolEffect.PROCESS_EXECUTE,),
                argument_constraints={"argv": ["pytest", "-q"]},
            ),
        ),
    )
    controller = SessionController(
        RuntimeDependencies(runtime=runtime, config=config), tmp_path, "fake"
    )

    tuple(controller.dispatch(ExecuteSlashCommand(raw="/permissions revoke")))

    assert runtime.workspace_permissions is not None
    assert runtime.workspace_permissions.trusted is False
    assert runtime.workspace_permissions.grants == ()


def test_permissions_rejects_unknown_scope_and_exposes_scope_summary(tmp_path: Path) -> None:
    runtime = VeraRuntime(FakeModelAdapter([]), ToolRegistry(), tmp_path / "state")
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
    snapshot = runtime.policy_engine.snapshot
    runtime.workspace_permissions = WorkspacePermissionSnapshot(
        workspace_identity=snapshot.workspace_identity,
        policy_major_version=snapshot.builtin_policy_version,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=True,
    )

    output = tuple(controller.dispatch(ExecuteSlashCommand(raw="/permissions nope")))
    event = next(item for item in output if isinstance(item, EventEnvelope))
    assert event.type == "session.message"
    assert "once" not in event.payload["text"]

    output = tuple(controller.dispatch(ExecuteSlashCommand(raw="/permissions")))
    event = next(item for item in output if isinstance(item, EventEnvelope))
    assert event.type == "session.permissions"
    assert event.payload["trusted"] is True
    assert event.payload["approval_scopes"] == ["once", "run", "workspace"]


def test_permissions_trust_is_persisted_for_the_current_workspace(tmp_path: Path) -> None:
    runtime = VeraRuntime(FakeModelAdapter([]), ToolRegistry(), tmp_path / "state")
    config = VeraConfig(
        state_dir=tmp_path / "state",
        limits=Limits(),
        providers={
            "fake": ProviderConfig(
                base_url="https://example.invalid", model="fake", api_key_env="FAKE_API_KEY"
            )
        },
    )
    snapshot = runtime.policy_engine.snapshot
    runtime.workspace_permissions = WorkspacePermissionSnapshot(
        workspace_identity=snapshot.workspace_identity,
        policy_major_version=snapshot.builtin_policy_version,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=False,
    )
    controller = SessionController(
        RuntimeDependencies(runtime=runtime, config=config), tmp_path, "fake"
    )

    tuple(controller.dispatch(ExecuteSlashCommand(raw="/permissions trust")))

    store = WorkspacePermissionStore(
        config.state_dir,
        policy_major_version=snapshot.builtin_policy_version,
        protected_roots_hash=snapshot.protected_roots_hash,
    )
    assert store.load(snapshot.workspace_identity).trusted is True
