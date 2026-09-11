"""Read-only workspace hashing for recovery classification."""

from __future__ import annotations

import hashlib
from pathlib import Path

from vera.contracts.recovery import FileRecoveryState, RecoveryEvidence
from vera.recovery.models import RecoverySnapshot
from vera.workspace.changeset import ABSENT_HASH, sha256_bytes
from vera.workspace.paths import WorkspaceBoundaryError, WorkspacePaths


def workspace_identity(workspace: Path, installation_id: str) -> str:
    payload = f"{installation_id}\0{workspace.resolve()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class WorkspaceEvidenceProbe:
    def __init__(self, installation_id: str) -> None:
        self.installation_id = installation_id

    def identity_matches(self, snapshot: RecoverySnapshot) -> bool:
        return snapshot.workspace_identity == workspace_identity(
            snapshot.workspace_root, self.installation_id
        )

    def workspace_available(self, snapshot: RecoverySnapshot) -> bool:
        try:
            root = snapshot.workspace_root.expanduser().resolve()
        except OSError:
            return False
        return root.is_dir()

    def inspect(self, snapshot: RecoverySnapshot) -> tuple[RecoveryEvidence, ...]:
        built = snapshot.built_changeset
        if built is None:
            return ()
        try:
            paths = WorkspacePaths(snapshot.workspace_root)
        except (OSError, WorkspaceBoundaryError):
            return tuple(
                RecoveryEvidence(
                    path=item.path,
                    before_hash=item.before_hash,
                    after_hash=item.after_hash,
                    current_hash=ABSENT_HASH,
                    state=FileRecoveryState.UNKNOWN,
                )
                for item in built.change_set.files
            )
        evidence: list[RecoveryEvidence] = []
        for item in built.change_set.files:
            evidence.append(self._inspect_file(paths, item.path, item.before_hash, item.after_hash))
        return tuple(evidence)

    @staticmethod
    def _inspect_file(
        paths: WorkspacePaths,
        relative: str,
        before_hash: str,
        after_hash: str,
    ) -> RecoveryEvidence:
        try:
            target = paths.resolve_mutation(relative)
            current_hash = ABSENT_HASH if not target.exists() else sha256_bytes(target.read_bytes())
        except (OSError, ValueError, WorkspaceBoundaryError):
            return RecoveryEvidence(
                path=relative,
                before_hash=before_hash,
                after_hash=after_hash,
                current_hash=ABSENT_HASH,
                state=FileRecoveryState.UNKNOWN,
            )
        if current_hash == before_hash:
            state = FileRecoveryState.BEFORE
        elif current_hash == after_hash:
            state = FileRecoveryState.AFTER
        else:
            state = FileRecoveryState.UNKNOWN
        return RecoveryEvidence(
            path=relative,
            before_hash=before_hash,
            after_hash=after_hash,
            current_hash=current_hash,
            state=state,
        )
