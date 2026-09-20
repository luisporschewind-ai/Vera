"""Single dependency assembly point for the CLI."""

import json
import os
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from vera.config import ConfigurationError, VeraConfig, load_config, load_provider_environment
from vera.models.base import ModelAdapter
from vera.models.openai_compatible import OpenAICompatibleAdapter
from vera.persistence.recovery_snapshot import RecoverySnapshotStore
from vera.persistence.workspace_permissions import (
    WorkspacePermissionStore,
    WorkspacePermissionStoreError,
)
from vera.policy.engine import PolicyEngine
from vera.policy.snapshot import EffectivePolicySnapshotV2
from vera.project_instructions import ProjectInstructionService
from vera.recovery.coordinator import RecoveryCoordinator
from vera.recovery.probe import workspace_identity
from vera.runtime.engine import VeraRuntime
from vera.tools.bash import BashTool
from vera.tools.builtin import FindTool, GrepTool, LsTool, ReadTool
from vera.tools.command_policy import CommandPolicy
from vera.tools.file_mutation import EditTool, WriteTool
from vera.tools.git import (
    GitBranchListTool,
    GitDiffTool,
    GitLogTool,
    GitShowTool,
    GitStatusTool,
)
from vera.tools.registry import ToolRegistry
from vera.workspace.paths import WorkspacePaths


@dataclass(frozen=True)
class RuntimeDependencies:
    runtime: VeraRuntime
    config: VeraConfig
    installation_id: str = ""
    project_instructions: ProjectInstructionService = field(
        default_factory=ProjectInstructionService
    )


type RuntimeBuilder = Callable[[Path, str | None], RuntimeDependencies]


def load_or_create_installation_id(state_dir: Path) -> str:
    path = state_dir / "installation.json"
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            installation_id = str(payload["installation_id"])
            if installation_id:
                return installation_id
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass
    state_dir.mkdir(parents=True, exist_ok=True)
    with suppress(OSError):
        os.chmod(state_dir, 0o700)
    installation_id = uuid4().hex
    temporary = state_dir / "installation.json.tmp"
    body = json.dumps(
        {"installation_id": installation_id},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    os.chmod(path, 0o600)
    return installation_id


def build_runtime(workspace: Path, model_profile: str | None = None) -> RuntimeDependencies:
    load_provider_environment()
    config = load_config(workspace, {})
    try:
        installation_id = load_or_create_installation_id(config.state_dir)
    except OSError as exc:
        raise ConfigurationError(
            "state_unwritable",
            f"private state directory is not writable: {config.state_dir}",
        ) from exc
    profile = model_profile or next(iter(config.providers), None)
    if profile is None or profile not in config.providers:
        raise ConfigurationError("missing_provider_config", "no model provider configured")
    provider = config.providers[profile]
    adapter: ModelAdapter = OpenAICompatibleAdapter(provider)
    paths = WorkspacePaths(workspace)
    registry = ToolRegistry()
    registry.register(ReadTool(paths, config.limits.max_file_bytes))
    registry.register(WriteTool(workspace, config.state_dir))
    registry.register(EditTool(workspace, config.state_dir))
    registry.register(GrepTool(paths))
    registry.register(FindTool(paths))
    registry.register(LsTool(paths))
    registry.register(BashTool(workspace))
    registry.register(GitStatusTool(workspace))
    registry.register(GitDiffTool(workspace))
    registry.register(GitLogTool(workspace))
    registry.register(GitShowTool(workspace))
    registry.register(GitBranchListTool(workspace))
    policy_prefixes = config.user_allowed_command_prefixes
    identity = workspace_identity(workspace, installation_id)
    effective_snapshot = EffectivePolicySnapshotV2(
        workspace_identity=identity,
        user_allowed_command_prefixes=policy_prefixes,
    )
    permission_store = WorkspacePermissionStore(
        config.state_dir,
        policy_major_version=effective_snapshot.builtin_policy_version,
        protected_roots_hash=effective_snapshot.protected_roots_hash,
    )
    try:
        workspace_permissions = permission_store.load(identity)
    except WorkspacePermissionStoreError as exc:
        raise ConfigurationError("permissions_unavailable", "无法读取工作区权限状态") from exc
    engine = PolicyEngine(effective_snapshot)
    policy = CommandPolicy(
        policy_prefixes,
        policy_engine=engine,
        workspace_identity=identity,
    )
    snapshot_store = RecoverySnapshotStore(config.state_dir)
    coordinator = RecoveryCoordinator(
        config.state_dir,
        installation_id,
        snapshot_store=snapshot_store,
    )
    project_instructions = ProjectInstructionService()
    runtime = VeraRuntime(
        adapter,
        registry,
        config.state_dir,
        config.limits,
        command_policy=policy,
        snapshot_store=snapshot_store,
        installation_id=installation_id,
        recovery_coordinator=coordinator,
        policy_engine=engine,
        project_instructions=project_instructions,
        workspace_permissions=workspace_permissions,
    )
    return RuntimeDependencies(
        runtime=runtime,
        config=config,
        installation_id=installation_id,
        project_instructions=project_instructions,
    )
