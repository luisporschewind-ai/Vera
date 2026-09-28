"""Single dependency assembly point for the CLI."""

import json
import os
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from vera.config import ConfigurationError, VeraConfig, load_config
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
from vera.provider_catalog import CATALOG_BY_ID, MODEL_CATALOG
from vera.provider_configuration import ProviderConfigurationService
from vera.provider_credentials import (
    provider_env_path,
    read_provider_environment,
    validate_key_name,
)
from vera.recovery.coordinator import RecoveryCoordinator
from vera.recovery.probe import workspace_identity
from vera.runtime.engine import VeraRuntime
from vera.sandbox.access import AccessSession
from vera.sandbox.files import PermissionPaths
from vera.sandbox.settings import load_backend, settings_path
from vera.sandbox.supervision import SandboxedSupervisor
from vera.sandbox.tools import RequestFileAccessTool
from vera.sandbox.writer import PermissionFileWriter
from vera.skills.discovery import SkillDiscovery
from vera.skills.registry import SkillRegistry
from vera.skills.selection import SkillSelectionService
from vera.skills.snapshot_store import SkillSnapshotStore
from vera.tools.bash import BashTool
from vera.tools.builtin import FindTool, GrepTool, LsTool, ReadTool
from vera.tools.command_policy import CommandPolicy
from vera.tools.file_mutation import EditTool, WriteTool
from vera.tools.git import (
    GitBranchCreateTool,
    GitBranchListTool,
    GitBranchSwitchTool,
    GitCommitTool,
    GitDiffTool,
    GitLogTool,
    GitRepositoryInitTool,
    GitShowTool,
    GitStatusTool,
)
from vera.tools.registry import ToolRegistry


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
    preliminary = load_config(workspace, {})
    profiles = ProviderConfigurationService()
    trusted_names = {provider.api_key_env for provider in preliminary.providers.values()}
    trusted_names.update(item.api_key_env for item in MODEL_CATALOG)
    trusted_names.update(item.api_key_env for item in profiles.list_profiles())
    for name in trusted_names:
        validate_key_name(name)
    source = provider_env_path()
    if source.is_symlink():
        raise ConfigurationError("unsafe_provider_env", "provider key file is unsafe")
    if source.exists() or source.is_symlink():
        workspace_root = workspace.resolve(strict=True)
        private_file = source.resolve(strict=True)
        if private_file == workspace_root or workspace_root in private_file.parents:
            raise ConfigurationError(
                "provider_key_in_workspace", "provider key file is inside workspace"
            )
    values = read_provider_environment(
        frozenset(
            trusted_names
            | {
                "VERA_DEEPSEEK_BASE_URL",
                "VERA_DEEPSEEK_MODEL",
                "VERA_GLM_BASE_URL",
                "VERA_GLM_MODEL",
            }
        ),
        source,
    )
    config = load_config(workspace, {}, values)
    if profiles.path.exists():
        profile = model_profile or config.default_model_profile
        if profile is None:
            raise ConfigurationError("missing_provider_config", "select and enable a model profile")
    else:
        profile = (
            model_profile or config.default_model_profile or next(iter(config.providers), None)
        )
    if profile is None or profile not in config.providers:
        raise ConfigurationError("missing_provider_config", "no model provider configured")
    provider = config.providers[profile]
    api_key = os.environ.get(provider.api_key_env) or values.get(provider.api_key_env)
    if not api_key:
        raise ConfigurationError("missing_provider_key", "selected model API Key is not configured")
    try:
        installation_id = load_or_create_installation_id(config.state_dir)
    except OSError as exc:
        raise ConfigurationError(
            "state_unwritable",
            f"private state directory is not writable: {config.state_dir}",
        ) from exc
    catalog_entry = CATALOG_BY_ID.get(profile)
    adapter: ModelAdapter = OpenAICompatibleAdapter(
        provider,
        api_key=api_key,
        profile_name=profile,
        provider_type=catalog_entry.provider_id if catalog_entry else "custom",
    )
    access_session = AccessSession(
        workspace,
        private_roots=(
            config.state_dir,
            source,
            settings_path().parent,
            workspace / ".vera",
            Path.home() / ".ssh",
            Path.home() / ".aws",
            Path.home() / ".gnupg",
            Path.home() / "Library/Keychains",
            *(
                Path(os.environ[key])
                for key in ("VERA_PROVIDER_ENV_FILE", "VERA_USER_CONFIG_FILE")
                if os.environ.get(key)
            ),
        ),
    )
    paths = PermissionPaths(access_session)
    supervisor = SandboxedSupervisor(access_session, load_backend())
    registry = ToolRegistry()
    registry.register(ReadTool(paths, config.limits.max_file_bytes))
    registry.register(WriteTool(workspace, config.state_dir, paths=paths))
    registry.register(EditTool(workspace, config.state_dir, paths=paths))
    registry.register(GrepTool(paths))
    registry.register(FindTool(paths))
    registry.register(LsTool(paths))
    registry.register(BashTool(workspace, supervisor=supervisor))
    registry.register(GitCommitTool(workspace, supervisor=supervisor))
    registry.register(GitStatusTool(workspace, supervisor=supervisor))
    registry.register(GitDiffTool(workspace, supervisor=supervisor))
    registry.register(GitLogTool(workspace, supervisor=supervisor))
    registry.register(GitShowTool(workspace, supervisor=supervisor))
    registry.register(GitBranchListTool(workspace, supervisor=supervisor))
    registry.register(GitBranchCreateTool(workspace, supervisor=supervisor))
    registry.register(GitBranchSwitchTool(workspace, supervisor=supervisor))
    registry.register(GitRepositoryInitTool(workspace))
    registry.register(RequestFileAccessTool(access_session, registry))
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
    skill_selection_service = SkillSelectionService(SkillRegistry(SkillDiscovery()))
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
        access_session=access_session,
        process_supervisor=supervisor,
        file_writer=PermissionFileWriter(paths),
        skill_selection_service=skill_selection_service,
        skill_snapshot_store=SkillSnapshotStore(),
    )
    return RuntimeDependencies(
        runtime=runtime,
        config=config,
        installation_id=installation_id,
        project_instructions=project_instructions,
    )
