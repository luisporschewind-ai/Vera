"""Private, recoverable snapshots for a proposed ChangeSet."""

import base64
import json
import os
import re
from pathlib import Path

from vera.contracts.changes import ChangeSet
from vera.contracts.checkpoints import CheckpointFile, CheckpointManifest
from vera.contracts.errors import classify_os_error
from vera.contracts.file_mutations import FileMutationCheckpoint, FileMutationPlan
from vera.persistence.errors import PersistenceFault
from vera.workspace.changeset import sha256_bytes
from vera.workspace.paths import WorkspaceBoundaryError, WorkspacePaths


class CheckpointStore:
    def __init__(self, state_dir: Path, paths: WorkspacePaths) -> None:
        self.state_dir = state_dir.expanduser().resolve()
        self.paths = paths

    def _directory(self, run_id: str) -> Path:
        directory = self.state_dir / "runs" / run_id / "checkpoint"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)
        return directory

    def create(self, change_set: ChangeSet) -> CheckpointManifest:
        directory = self._directory(change_set.run_id)
        blobs = directory / "blobs"
        blobs.mkdir(exist_ok=True, mode=0o700)
        os.chmod(blobs, 0o700)
        before: dict[str, CheckpointFile] = {}
        for change in change_set.files:
            try:
                fact = self.paths.inspect_mutation(change.path)
            except WorkspaceBoundaryError:
                raise
            target = Path(fact.canonical_path)
            if fact.exists:
                if fact.kind != "regular":
                    raise WorkspaceBoundaryError(
                        f"checkpoint requires a regular file: {change.path}",
                        code="not_regular_file",
                    )
                data = target.read_bytes()
                content_hash = sha256_bytes(data)
                if change.before_hash != content_hash:
                    raise ValueError(f"before hash changed: {change.path}")
                blob = blobs / f"{content_hash}.bin"
                if not blob.exists():
                    blob.write_bytes(data)
                    os.chmod(blob, 0o600)
                before[change.path] = CheckpointFile(
                    existed=True,
                    content_hash=content_hash,
                    mode=fact.mode if fact.mode is not None else target.stat().st_mode & 0o777,
                )
            else:
                if change.before_hash != "0" * 64:
                    raise ValueError(f"before existence changed: {change.path}")
                before[change.path] = CheckpointFile(existed=False)
        manifest = CheckpointManifest(
            checkpoint_id=f"checkpoint_{change_set.changeset_id}",
            run_id=change_set.run_id,
            workspace_root=self.paths.root,
            before=before,
            after_hashes={item.path: item.after_hash for item in change_set.files},
        )
        temporary = directory / "manifest.json.tmp"
        temporary.write_text(
            json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, directory / "manifest.json")
        return manifest

    def load_for_run(self, run_id: str) -> CheckpointManifest:
        return self.load_manifest(self.state_dir, run_id)

    @staticmethod
    def load_manifest(state_dir: Path, run_id: str) -> CheckpointManifest:
        if Path(run_id).name != run_id:
            raise FileNotFoundError(run_id)
        manifest_path = (
            state_dir.expanduser().resolve() / "runs" / run_id / "checkpoint" / "manifest.json"
        )
        try:
            text = manifest_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise PersistenceFault("invalid_encoding", "checkpoint manifest is not utf-8") from exc
        except OSError as exc:
            raise PersistenceFault(classify_os_error(exc), str(exc)) from exc
        return CheckpointManifest.model_validate_json(text)

    def read_original(self, manifest: CheckpointManifest, path: str) -> bytes:
        record = manifest.before[path]
        if not record.existed or record.content_hash is None:
            raise FileNotFoundError(path)
        blob = (
            self.state_dir
            / "runs"
            / manifest.run_id
            / "checkpoint"
            / "blobs"
            / f"{record.content_hash}.bin"
        )
        data = blob.read_bytes()
        if sha256_bytes(data) != record.content_hash:
            raise ValueError(f"checkpoint blob hash mismatch: {path}")
        return data


class FileMutationCheckpointStore:
    """Private checkpoint storage for one write/edit action."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir.expanduser().resolve()

    def path_for(self, run_id: str, action_id: str) -> Path:
        if not _safe_component(run_id) or not _safe_component(action_id):
            raise ValueError("unsafe mutation checkpoint identity")
        return self.state_dir / "runs" / run_id / "mutations" / f"{action_id}.json"

    def create(
        self,
        plan: FileMutationPlan,
        before: bytes,
        mode: int | None,
        *,
        workspace_root: Path,
    ) -> FileMutationCheckpoint:
        checkpoint = FileMutationCheckpoint(
            action_id=plan.action_id,
            run_id=plan.run_id,
            workspace_root=workspace_root,
            path=plan.path,
            before_exists=plan.before_hash != "0" * 64,
            before_hash=plan.before_hash,
            before_content_b64=base64.b64encode(before).decode("ascii"),
            before_mode=mode,
            after_hash=plan.after_hash,
        )
        path = self.path_for(plan.run_id, plan.action_id)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(checkpoint.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        return checkpoint

    def load(self, run_id: str, action_id: str) -> FileMutationCheckpoint:
        path = self.path_for(run_id, action_id)
        return FileMutationCheckpoint.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def before_bytes(checkpoint: FileMutationCheckpoint) -> bytes:
        try:
            data = base64.b64decode(checkpoint.before_content_b64.encode("ascii"), validate=True)
        except Exception as exc:
            raise ValueError("invalid mutation checkpoint content") from exc
        if sha256_bytes(data) != checkpoint.before_hash and checkpoint.before_exists:
            raise ValueError("mutation checkpoint before hash mismatch")
        if not checkpoint.before_exists and data:
            raise ValueError("absent mutation checkpoint contains content")
        return data


_SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _safe_component(value: str) -> bool:
    return _SAFE_COMPONENT_RE.fullmatch(value) is not None
