"""Installed-wheel Core smoke payload.

The payload remains a source string so the smoke test imports the installed wheel.
"""

_CORE_SMOKE = r"""
import os
import subprocess
import sys
from pathlib import Path

from vera.policy.engine import PolicyEngine
from vera.policy.permissions import WorkspacePermissionSnapshot
from vera.policy.snapshot import EffectivePolicySnapshotV2
from vera.recovery.probe import workspace_identity
from vera.tools.bash import BashTool
from vera.tools.builtin import ReadTool
from vera.tools.executor import ToolExecutor
from vera.tools.file_mutation import EditTool, WriteTool
from vera.tools.git import GitCommitTool, GitStatusTool
from vera.tools.registry import ToolRegistry
from vera.workspace.paths import WorkspacePaths

root = Path(sys.argv[1]).resolve()
state = root.parent / "state"
root.mkdir(parents=True, exist_ok=True)
identity = workspace_identity(root, "installed-smoke")
policy = EffectivePolicySnapshotV2(workspace_identity=identity)
permissions = WorkspacePermissionSnapshot(
    workspace_identity=identity,
    policy_major_version=policy.builtin_policy_version,
    protected_roots_hash=policy.protected_roots_hash,
    trusted=True,
)
registry = ToolRegistry()
registry.register(ReadTool(WorkspacePaths(root), 100_000))
registry.register(WriteTool(root, state))
registry.register(EditTool(root, state))
registry.register(BashTool(root))
registry.register(GitStatusTool(root))
registry.register(GitCommitTool(root))
executor = ToolExecutor(
    registry,
    PolicyEngine(policy),
    permissions,
    goal_authorized=True,
    state_dir=state,
)

write = executor.prepare(
    run_id="installed-smoke",
    name="write",
    arguments={"path": "app.py", "content": "value = 1\n"},
)
assert executor.execute_allowed(write).ok
edit = executor.prepare(
    run_id="installed-smoke",
    name="edit",
    arguments={"path": "app.py", "old_text": "value = 1", "new_text": "value = 2"},
)
assert executor.execute_allowed(edit).ok
read = executor.prepare(
    run_id="installed-smoke", name="read", arguments={"path": "app.py"}
)
assert executor.execute_allowed(read).ok
shell = executor.prepare(
    run_id="installed-smoke", name="bash", arguments={"argv": ["sh", "-c", "echo bad"]}
)
assert shell.policy_decision.decision.value == "deny"

env = os.environ.copy()
env.update(
    {
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Vera Smoke",
        "GIT_AUTHOR_EMAIL": "smoke@example.invalid",
        "GIT_COMMITTER_NAME": "Vera Smoke",
        "GIT_COMMITTER_EMAIL": "smoke@example.invalid",
        "GIT_TERMINAL_PROMPT": "0",
    }
)
subprocess.run(["git", "init", "-q"], cwd=root, env=env, check=True)
subprocess.run(["git", "config", "user.name", "Vera Smoke"], cwd=root, env=env, check=True)
subprocess.run(
    ["git", "config", "user.email", "smoke@example.invalid"], cwd=root, env=env, check=True
)
subprocess.run(["git", "add", "--", "app.py"], cwd=root, env=env, check=True)
subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, env=env, check=True)
status = executor.prepare(run_id="installed-smoke", name="git_status", arguments={})
assert executor.execute_allowed(status).ok
(root / "commit.txt").write_text("installed\n", encoding="utf-8")
commit = executor.prepare(
    run_id="installed-smoke",
    name="git_commit",
    arguments={
        "paths": ["commit.txt"],
        "message": "Installed smoke commit",
        "action_ids": ["installed-smoke-action"],
        "verification_status": "passed",
    },
)
assert executor.execute_allowed(commit).ok
assert subprocess.run(
    ["git", "show", "-s", "--format=%s"], cwd=root, env=env, check=True,
    capture_output=True, text=True,
).stdout.strip() == "Installed smoke commit"
"""
