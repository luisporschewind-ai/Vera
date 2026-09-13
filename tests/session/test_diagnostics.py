from pathlib import Path

from vera.config import Limits, ProviderConfig, VeraConfig
from vera.session.diagnostics import doctor_report, redacted_config_view


def test_doctor_and_config_never_leak_secrets(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    report = doctor_report(
        workspace=workspace,
        state_dir=state,
        user_config=tmp_path / "missing.toml",
        tty=False,
        term="dumb",
    )
    names = {item["name"] for item in report["items"]}
    assert names == {"version", "python", "terminal", "config", "state_dir", "git"}
    version_item = next(item for item in report["items"] if item["name"] == "version")
    assert "0.1.0" in version_item["detail"]
    assert "vera" in version_item["detail"]
    dumped = str(report)
    assert "sk-" not in dumped
    assert "api_key" not in dumped

    config = VeraConfig(
        state_dir=state,
        limits=Limits(),
        providers={
            "fake": ProviderConfig(
                base_url="https://example.invalid",
                model="fake-model",
                api_key_env="FAKE_API_KEY",
            )
        },
    )
    view = redacted_config_view(config, {"user": "absent"})
    assert "FAKE_API_KEY" in str(view)
    assert "sk-" not in str(view)
    assert view["sources"]["user"] == "absent"
