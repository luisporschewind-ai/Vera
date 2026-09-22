from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.skills.test_manifest import write_skill
from vera.skills.manifest import ManifestLoader
from vera.skills.snapshot_codec import SkillSnapshotCodec, SkillSnapshotCodecError
from vera.skills.snapshot_store import SkillSnapshotStore


def test_skill_snapshot_codec_round_trips_private_frozen_payload(tmp_path: Path) -> None:
    package = ManifestLoader().load(write_skill(tmp_path / "source"), source_kind="user")
    frozen = SkillSnapshotStore().freeze(package, state_dir=tmp_path / "state")

    restored = SkillSnapshotCodec().decode(SkillSnapshotCodec().encode(frozen))

    assert restored.snapshot == frozen.snapshot
    assert restored.context_files() == frozen.context_files()
    assert "# Skill" not in SkillSnapshotCodec().encode(frozen).decode("utf-8")


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda payload: payload.update({"snapshot_format_version": 99}),
            "skill_snapshot_version_unsupported",
        ),
        (lambda payload: payload.pop("files"), "skill_snapshot_corrupt"),
    ],
)
def test_skill_snapshot_codec_rejects_bad_shape(tmp_path: Path, mutate, expected: str) -> None:
    package = ManifestLoader().load(write_skill(tmp_path / "source"), source_kind="user")
    frozen = SkillSnapshotStore().freeze(package, state_dir=tmp_path / "state")
    payload = json.loads(SkillSnapshotCodec().encode(frozen))
    mutate(payload)

    with pytest.raises(SkillSnapshotCodecError, match=expected):
        SkillSnapshotCodec().decode(json.dumps(payload))
