from __future__ import annotations

import json

from typer.testing import CliRunner

from vera.cli import app
from vera.evals.corpus import CorpusLoader


def test_eval_validate_matches_loader() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["eval", "validate", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    current = CorpusLoader().validate()
    assert payload["schema_version"] == 1
    assert payload["manifest_hash"] == current.manifest_hash
    assert len(payload["case_ids"]) == 14
