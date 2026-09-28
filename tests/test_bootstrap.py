from pathlib import Path

import pytest

from vera.bootstrap import build_runtime


def test_runtime_and_session_store_share_installation_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "deepseek.env"
    source.write_text(
        "DEEPSEEK_API_KEY=test-secret\n"
        "VERA_DEEPSEEK_BASE_URL=https://api.deepseek.com\n"
        "VERA_DEEPSEEK_MODEL=deepseek-flash\n",
        encoding="utf-8",
    )
    source.chmod(0o600)
    monkeypatch.setenv("VERA_PROVIDER_ENV_FILE", str(source))
    monkeypatch.setenv("VERA_STATE_DIR", str(tmp_path / "state"))
    dependencies = build_runtime(tmp_path)
    assert dependencies.installation_id
    assert dependencies.installation_id == dependencies.runtime.installation_id
    tool_names = {definition.name for definition in dependencies.runtime.registry.definitions()}
    assert {
        "git_status",
        "git_diff",
        "git_log",
        "git_show",
        "git_branch_list",
    } <= tool_names
