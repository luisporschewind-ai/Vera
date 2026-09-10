from typer.testing import CliRunner

from vera.cli import app


def test_rollback_requires_target() -> None:
    result = CliRunner().invoke(app, ["rollback"])
    assert result.exit_code != 0


def test_rollback_missing_run_is_explicit_and_does_not_create_record(
    tmp_path, monkeypatch
) -> None:
    state_dir = tmp_path / "state"
    monkeypatch.setenv("VERA_STATE_DIR", str(state_dir))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-secret")
    monkeypatch.setenv("VERA_DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("VERA_DEEPSEEK_MODEL", "deepseek-flash")

    result = CliRunner().invoke(app, ["rollback", "run_missing"])

    assert result.exit_code == 5
    assert "未找到可回滚的 Checkpoint" in result.stdout
    assert not (state_dir / "runs" / "run_missing").exists()
