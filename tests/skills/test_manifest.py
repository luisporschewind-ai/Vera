from pathlib import Path

import pytest

from vera.skills.manifest import ManifestLoader, SkillValidationError


def write_skill(
    root: Path,
    *,
    name: str = "python-review",
    manifest: str | None = None,
    body: bytes = b"# Skill\n",
) -> Path:
    package = root / name
    package.mkdir(parents=True)
    manifest_text = (
        manifest
        or """
format_version = 1
name = "python-review"
version = "1.0.0"
description = "Review Python projects"

[compatibility]
min_vera_core = "0.1.0"
max_vera_core_exclusive = "1.0.0"

[resources]
references = ["references/checklist.md"]
templates = ["templates/report.md"]
"""
    )
    (package / "skill.toml").write_text(
        manifest_text.replace('name = "python-review"', f'name = "{name}"'),
        encoding="utf-8",
    )
    (package / "SKILL.md").write_bytes(body)
    (package / "references").mkdir()
    (package / "references" / "checklist.md").write_text("checklist\n", encoding="utf-8")
    (package / "templates").mkdir()
    (package / "templates" / "report.md").write_text("report\n", encoding="utf-8")
    return package


def test_manifest_loader_returns_normalized_package_without_public_body(tmp_path: Path) -> None:
    package = write_skill(tmp_path)

    loaded = ManifestLoader().load(package, source_kind="user")

    assert loaded.manifest.name == "python-review"
    assert loaded.skill_id == "user:python-review"
    assert [item.relative_path for item in loaded.files] == [
        "SKILL.md",
        "references/checklist.md",
        "templates/report.md",
    ]
    assert loaded.manifest_hash and len(loaded.manifest_hash) == 64
    assert loaded.resource_hash and len(loaded.resource_hash) == 64
    assert "# Skill" not in loaded.public_facts_json()


@pytest.mark.parametrize(
    ("marker", "expected"),
    [
        ("unknown = true\n", "skill_manifest_invalid"),
        ('name = "Bad_Name"\n', "skill_manifest_invalid"),
        ('version = "1"\n', "skill_manifest_invalid"),
        ("format_version = 2\n", "skill_manifest_version_unsupported"),
        ('[resources]\nreferences = ["../escape.md"]\n', "skill_path_escape"),
        ('[resources]\nreferences = ["/absolute.md"]\n', "skill_path_escape"),
        (
            '[resources]\nreferences = ["references/a.md", "references/./a.md"]\n',
            "skill_resource_invalid",
        ),
    ],
)
def test_manifest_loader_rejects_invalid_manifest(
    tmp_path: Path, marker: str, expected: str
) -> None:
    manifest = write_skill(tmp_path).joinpath("skill.toml")
    original = manifest.read_text(encoding="utf-8")
    if marker.startswith("unknown"):
        updated = original + marker
    elif marker.startswith("name"):
        updated = original.replace('name = "python-review"', marker.strip())
    elif marker.startswith("version"):
        updated = original.replace('version = "1.0.0"', marker.strip())
    elif marker.startswith("format_version"):
        updated = original.replace("format_version = 1", marker.strip())
    else:
        updated = original.replace(
            '[resources]\nreferences = ["references/checklist.md"]', marker.rstrip()
        )
    manifest.write_text(updated, encoding="utf-8")

    with pytest.raises(SkillValidationError) as caught:
        ManifestLoader().load(manifest.parent, source_kind="user")

    assert caught.value.code == expected


def test_manifest_loader_rejects_missing_declared_resource_and_symlink(tmp_path: Path) -> None:
    package = write_skill(tmp_path)
    (package / "references" / "checklist.md").unlink()
    with pytest.raises(SkillValidationError, match="skill_resource_missing"):
        ManifestLoader().load(package, source_kind="user")

    package = write_skill(tmp_path / "second")
    target = package / "templates" / "report.md"
    target.unlink()
    target.symlink_to(package / "SKILL.md")
    with pytest.raises(SkillValidationError, match="skill_symlink_refused"):
        ManifestLoader().load(package, source_kind="user")


def test_manifest_loader_rejects_package_limits_and_invalid_utf8(tmp_path: Path) -> None:
    package = write_skill(tmp_path, body=b"x" * (64 * 1024 + 1))
    with pytest.raises(SkillValidationError, match="skill_package_limit_exceeded"):
        ManifestLoader().load(package, source_kind="user")

    package = write_skill(tmp_path / "invalid", body=b"\xff")
    with pytest.raises(SkillValidationError, match="skill_resource_invalid"):
        ManifestLoader().load(package, source_kind="user")
