from pathlib import Path

import pytest


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    value = tmp_path / "state"
    value.mkdir()
    return value


def write_toml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
