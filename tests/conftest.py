from pathlib import Path

import pytest

from vera.evals.corpus import CorpusLoader
from vera.evals.runner import EvalSuiteRunner


@pytest.fixture(autouse=True)
def isolate_real_provider_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent non-live tests from reading or using the user's provider credentials."""

    monkeypatch.setenv("VERA_PROVIDER_ENV_FILE", str(tmp_path / "no-provider.env"))
    for name in (
        "DEEPSEEK_API_KEY",
        "VERA_DEEPSEEK_BASE_URL",
        "VERA_DEEPSEEK_MODEL",
        "GLM_API_KEY",
        "VERA_GLM_BASE_URL",
        "VERA_GLM_MODEL",
        "VERA_LIVE_PROVIDER",
        "VERA_LIVE_BASE_URL",
        "VERA_LIVE_MODEL",
        "VERA_LIVE_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    value = tmp_path / "state"
    value.mkdir()
    return value


def write_toml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def corpus_loader() -> CorpusLoader:
    return CorpusLoader()


@pytest.fixture
def eval_runner(tmp_path: Path) -> EvalSuiteRunner:
    return EvalSuiteRunner(isolator_root=tmp_path / "isolator")
