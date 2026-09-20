import pytest
from pydantic import ValidationError

from vera.contracts.skills import SkillSelection, SkillSnapshot, SkillSummary


def test_public_skill_contracts_are_versioned_and_do_not_accept_extra_fields() -> None:
    summary = SkillSummary(
        skill_id="user:python-review",
        name="python-review",
        version="1.0.0",
        description="Review Python projects",
        source_kind="user",
        trust_level="advisory",
        availability="available",
        manifest_hash="a" * 64,
        resource_hash="b" * 64,
    )
    selection = SkillSelection(
        mode="explicit",
        selector="python-review",
        status="selected",
        skill_id="user:python-review",
        source_kind="user",
        version="1.0.0",
        manifest_hash="a" * 64,
    )
    snapshot = SkillSnapshot(
        snapshot_id="sha256:" + "c" * 64,
        skill_id="user:python-review",
        name="python-review",
        version="1.0.0",
        source_kind="user",
        manifest_hash="a" * 64,
        package_hash="d" * 64,
        resource_hash="b" * 64,
    )

    assert summary.schema_version == 1
    assert selection.schema_version == 1
    assert snapshot.schema_version == 1
    assert "secret body" not in summary.model_dump_json()

    with pytest.raises(ValidationError):
        SkillSummary.model_validate({**summary.model_dump(), "body": "secret"})


def test_invalid_summary_has_no_identity_or_hashes() -> None:
    summary = SkillSummary(
        source_kind="workspace",
        trust_level="untrusted",
        availability="invalid",
        reason_codes=("skill_manifest_invalid",),
    )

    assert summary.skill_id is None
    assert summary.name is None
    assert summary.version is None
    assert summary.manifest_hash is None
    assert summary.resource_hash is None
