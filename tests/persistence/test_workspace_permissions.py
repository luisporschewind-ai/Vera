from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from vera.contracts.tool_actions import ToolEffect
from vera.persistence.workspace_permissions import (
    WorkspacePermissionStore,
    WorkspacePermissionStoreError,
)
from vera.policy.permissions import PermissionGrant, WorkspacePermissionSnapshot

_PROTECTED_HASH = "a" * 64


def _snapshot(identity: str = "workspace_1") -> WorkspacePermissionSnapshot:
    return WorkspacePermissionSnapshot(
        workspace_identity=identity,
        policy_major_version=2,
        trusted=True,
        protected_roots_hash=_PROTECTED_HASH,
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


def _store(state_dir: Path, **kwargs) -> WorkspacePermissionStore:
    return WorkspacePermissionStore(
        state_dir,
        policy_major_version=2,
        protected_roots_hash=_PROTECTED_HASH,
        **kwargs,
    )


def test_permission_snapshot_is_atomic_private_and_round_trips(tmp_path: Path) -> None:
    store = _store(tmp_path / "state")
    snapshot = _snapshot()
    store.save(snapshot)

    target = store.path_for(snapshot.workspace_identity)
    assert store.load(snapshot.workspace_identity) == snapshot
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    assert not target.with_suffix(".json.tmp").exists()


def test_failed_atomic_replace_preserves_previous_permissions(tmp_path: Path) -> None:
    store = _store(tmp_path / "state")
    original = _snapshot()
    store.save(original)

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("injected replace failure")

    failing = _store(tmp_path / "state", replace=fail_replace)
    changed = original.model_copy(update={"trusted": False, "grants": ()})
    with pytest.raises(WorkspacePermissionStoreError, match="permission_write_failed"):
        failing.save(changed)

    assert store.load(original.workspace_identity) == original
    assert not store.path_for(original.workspace_identity).with_suffix(".json.tmp").exists()


def test_corrupt_permissions_are_quarantined_and_fail_closed(tmp_path: Path) -> None:
    store = _store(tmp_path / "state")
    target = store.path_for("workspace_1")
    target.parent.mkdir(parents=True)
    target.parent.chmod(0o700)
    target.write_text("{broken", encoding="utf-8")
    target.chmod(0o600)

    with pytest.raises(WorkspacePermissionStoreError) as caught:
        store.load("workspace_1")
    assert caught.value.code == "mid_file_corrupt"
    assert not target.exists()
    quarantined = tuple(target.parent.glob(f"{target.name}.corrupt-*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_text(encoding="utf-8") == "{broken"
    assert store.load("workspace_1").trusted is False


def test_future_version_is_preserved_and_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path / "state")
    store.save(_snapshot())
    target = store.path_for("workspace_1")
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["schema_version"] = 99
    target.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(WorkspacePermissionStoreError) as caught:
        store.load("workspace_1")
    assert caught.value.code == "unsupported_version"
    assert caught.value.version == 99
    assert target.exists()
    assert not tuple(target.parent.glob(f"{target.name}.corrupt-*"))


@pytest.mark.parametrize("changed", ["identity", "policy", "protected_roots"])
def test_binding_change_invalidates_trust_and_grants(tmp_path: Path, changed: str) -> None:
    state = tmp_path / "state"
    store = _store(state)
    store.save(_snapshot())
    target = store.path_for("workspace_1")
    payload = json.loads(target.read_text(encoding="utf-8"))
    if changed == "identity":
        payload["workspace_identity"] = "workspace_other"
        target.write_text(json.dumps(payload), encoding="utf-8")
        loaded = store.load("workspace_1")
    elif changed == "policy":
        loaded = WorkspacePermissionStore(
            state,
            policy_major_version=3,
            protected_roots_hash=_PROTECTED_HASH,
        ).load("workspace_1")
    else:
        loaded = WorkspacePermissionStore(
            state,
            policy_major_version=2,
            protected_roots_hash="b" * 64,
        ).load("workspace_1")

    assert loaded.trusted is False
    assert loaded.grants == ()
    assert not target.exists()
    assert tuple(target.parent.glob(f"{target.name}.stale-*"))


def test_revoke_is_idempotent_and_repository_file_cannot_authorize(tmp_path: Path) -> None:
    state = tmp_path / "private-state"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "permissions.json").write_text(
        _snapshot().model_dump_json(),
        encoding="utf-8",
    )
    store = _store(state)

    assert store.load("workspace_1").trusted is False
    store.save(_snapshot())
    store.revoke("workspace_1")
    store.revoke("workspace_1")
    assert store.load("workspace_1").trusted is False


def test_store_rejects_transient_run_or_once_grants(tmp_path: Path) -> None:
    store = _store(tmp_path / "state")
    transient = PermissionGrant(
        grant_id="grant_1",
        scope="run",
        tool_name="bash",
        effects=(ToolEffect.PROCESS_EXECUTE,),
        argument_constraints={"argv": ["pytest", "-q"]},
        run_id="run_1",
    )
    snapshot = _snapshot().model_copy(update={"grants": (transient,)})

    with pytest.raises(WorkspacePermissionStoreError) as caught:
        store.save(snapshot)
    assert caught.value.code == "transient_grant_persistence_forbidden"
