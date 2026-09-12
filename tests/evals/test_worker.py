from __future__ import annotations

from pathlib import Path

import pytest

from vera.evals.contracts import EvalStatus, EvalWorkerRequest
from vera.evals.script_driver import ScriptedRunDriver
from vera.evals.worker import run_worker


def _request(loaded_and_isolated) -> EvalWorkerRequest:
    loaded, isolated = loaded_and_isolated
    return EvalWorkerRequest(
        evaluation_id="eval-1",
        case_id=loaded.case.case_id,
        corpus_root=loaded.corpus_root,
        workspace=isolated.workspace,
        state_dir=isolated.state_dir,
        staging_dir=isolated.staging_dir,
    )


def test_worker_returns_report_from_core_facts(loaded_and_isolated) -> None:
    result = run_worker(_request(loaded_and_isolated))
    assert result.report is not None
    assert result.report.status is EvalStatus.PASS
    assert result.report.event_types[-1] == "run.completed"
    assert result.error_code is None


def test_worker_maps_uncaught_runtime_error(loaded_and_isolated, monkeypatch) -> None:
    def raising_runtime_error(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("secret token leaked")

    monkeypatch.setattr(ScriptedRunDriver, "run", raising_runtime_error)
    result = run_worker(_request(loaded_and_isolated))
    assert result.error_code == "runtime_exception"
    assert result.report is None or result.report.status is not EvalStatus.PASS
    assert "secret" not in result.model_dump_json()


def test_worker_rejects_source_change_after_run(loaded_and_isolated) -> None:
    request = _request(loaded_and_isolated)
    loaded, _isolated = loaded_and_isolated
    (loaded.source_root / "case.json").write_text("{}\n", encoding="utf-8")
    result = run_worker(request)
    assert result.error_code in {"source_changed", "manifest_mismatch", "invalid_contract"}


def test_worker_cli_writes_result_atomically(loaded_and_isolated, tmp_path: Path, capsys) -> None:
    from vera.evals.codec import EvalCodec
    from vera.evals.worker import main as worker_main

    request = _request(loaded_and_isolated)
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    worker_main(["--request", str(request_path), "--result", str(result_path)])
    captured = capsys.readouterr()
    assert captured.out == ""
    restored = EvalCodec.decode_worker_result(result_path.read_text(encoding="utf-8"))
    assert restored.report is not None
    assert restored.report.status is EvalStatus.PASS
    with pytest.raises(SystemExit):
        worker_main(["--request", str(request_path), "--result", str(result_path)])
