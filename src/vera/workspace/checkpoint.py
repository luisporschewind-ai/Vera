"""Private, recoverable snapshots for a proposed ChangeSet."""

import json
import os
from pathlib import Path

from vera.contracts.changes import ChangeSet
from vera.contracts.checkpoints import CheckpointFile, CheckpointManifest
from vera.workspace.changeset import sha256_bytes
from vera.workspace.paths import WorkspacePaths


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
            target = self.paths.resolve_mutation(change.path)
            if target.exists():
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
                    mode=target.stat().st_mode & 0o777,
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
        return CheckpointManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))

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
