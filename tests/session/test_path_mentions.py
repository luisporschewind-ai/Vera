from pathlib import Path

from vera.session.path_mentions import suggest_path_mentions


def test_path_mentions_keep_spaces_cjk_and_skip_unsafe(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "src").mkdir()
    (workspace / "src" / "my file.txt").write_text("a", encoding="utf-8")
    (workspace / "说明.md").write_text("中文", encoding="utf-8")
    (workspace / ".hidden").write_text("no", encoding="utf-8")
    (workspace / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (workspace / "ignored.txt").write_text("skip", encoding="utf-8")
    (workspace / "link").symlink_to(tmp_path / "outside.txt")
    (tmp_path / "outside.txt").write_text("out", encoding="utf-8")
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "secret.json").write_text("{}", encoding="utf-8")

    all_mentions = suggest_path_mentions(workspace, "", state_dir=state_dir)
    paths = {item.relative_path for item in all_mentions}
    assert "src/my file.txt" in paths
    assert "说明.md" in paths
    assert ".hidden" not in paths
    assert "ignored.txt" not in paths
    assert "link" not in paths
    assert "secret.json" not in paths
    assert all(item.kind in {"file", "directory"} for item in all_mentions)

    cjk = suggest_path_mentions(workspace, "说")
    assert [item.display for item in cjk] == ["说明.md"]
    spaced = suggest_path_mentions(workspace, "src/my f")
    assert spaced[0].relative_path == "src/my file.txt"
