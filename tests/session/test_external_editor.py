from pathlib import Path

import pytest

from vera.session.external_editor import ExternalEditor, ExternalEditorError


def test_editor_rejects_empty_and_shell_syntax(tmp_path: Path) -> None:
    with pytest.raises(ExternalEditorError, match="no editor argv configured") as empty:
        ExternalEditor((), tmp_path)
    assert empty.value.code == "editor_unconfigured"
    with pytest.raises(ExternalEditorError, match="must not contain shell syntax") as forbidden:
        ExternalEditor(("sh", "-c", "echo $(whoami)"), tmp_path)
    assert forbidden.value.code == "editor_forbidden"
    with pytest.raises(ExternalEditorError, match="must not contain shell syntax"):
        ExternalEditor(("bash", "-c", "true; rm -rf /"), tmp_path)


def test_write_draft_is_private_and_cleanup_is_exact(tmp_path: Path) -> None:
    editor = ExternalEditor(("true",), tmp_path)
    sibling = tmp_path / "keep.md"
    sibling.write_text("keep", encoding="utf-8")
    path = editor.write_draft("draft text")
    assert path.parent == tmp_path
    assert path.name.startswith("vera-draft-")
    assert path.read_text(encoding="utf-8") == "draft text"
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    editor.cleanup(path)
    assert not path.exists()
    assert sibling.read_text(encoding="utf-8") == "keep"
    with pytest.raises(ExternalEditorError, match="outside draft dir") as refused:
        editor.cleanup(tmp_path.parent / "outside.md")
    assert refused.value.code == "cleanup_refused"


def test_run_reports_ok_unchanged_and_failed(tmp_path: Path) -> None:
    editor = ExternalEditor(("true",), tmp_path)
    path = editor.write_draft("same")
    unchanged = editor.run(path, runner=lambda argv: 0)
    assert unchanged.status == "unchanged"
    assert unchanged.changed is False

    def change(_argv: tuple[str, ...]) -> int:
        path.write_text("changed", encoding="utf-8")
        return 0

    ok = editor.run(path, runner=change)
    assert ok.status == "ok"
    assert ok.changed is True
    assert ok.text == "changed"
    failed = editor.run(path, runner=lambda argv: 2)
    assert failed.status == "failed"
    assert failed.changed is False
    editor.cleanup(path)


def test_preview_uses_placeholder_not_real_path(tmp_path: Path) -> None:
    editor = ExternalEditor(("/usr/bin/vim", "-f"), tmp_path)
    assert editor.preview() == ("/usr/bin/vim", "-f", "<draft>")


def test_run_uses_fixed_argv_without_shell(tmp_path: Path) -> None:
    seen: list[tuple[str, ...]] = []

    def runner(argv: tuple[str, ...]) -> int:
        seen.append(argv)
        Path(argv[-1]).write_text("edited", encoding="utf-8")
        return 0

    editor = ExternalEditor(("nano", "-t"), tmp_path)
    path = editor.write_draft("old")
    result = editor.run(path, runner=runner)
    assert seen == [("nano", "-t", str(path))]
    assert result.status == "ok"
    assert result.text == "edited"
    editor.cleanup(path)
