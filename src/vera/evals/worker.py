"""Isolated evaluation worker: Core Command/Event only, no provider env."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from vera.evals.codec import EvalCodec, EvalCodecError
from vera.evals.contracts import (
    DimensionStatus,
    EvalMetrics,
    EvalReport,
    EvalScore,
    EvalStatus,
    EvalWorkerRequest,
    EvalWorkerResult,
)
from vera.evals.corpus import CorpusError, CorpusLoader
from vera.evals.isolation import IsolatedEvalCase, IsolationError
from vera.evals.runtime_factory import EvalRuntimeFactory
from vera.evals.scoring import Scorer
from vera.evals.script_driver import EvalExecutionError, ScriptedRunDriver

_DECLARED_GATES = ("correctness", "safety", "recovery")


def run_worker(request: EvalWorkerRequest) -> EvalWorkerResult:
    try:
        loader = CorpusLoader(request.corpus_root)
        loaded = loader.load(request.case_id)
        isolated = IsolatedEvalCase(
            workspace=request.workspace,
            state_dir=request.state_dir,
            staging_dir=request.staging_dir,
            source_manifest_hash=loaded.manifest_hash,
            case_root=request.workspace.parent,
            temp_root=request.workspace.parent.parent,
        )
        runtime = EvalRuntimeFactory().create(loaded, isolated)
        execution = ScriptedRunDriver().execute(runtime, loaded, isolated)
        current = loader.validate().manifest_hash
        isolated.verify_source_unchanged(current)
        metrics = EvalMetrics()
        scores = Scorer().score(
            loaded.case,
            loaded.expect,
            execution.before_files,
            execution.after_files,
            execution.events,
            metrics,
        )
        status = _status_from_scores(scores)
        report = EvalReport(
            evaluation_id=request.evaluation_id,
            case_id=request.case_id,
            status=status,
            scores=scores,
            reason_codes=tuple(sorted({code for score in scores for code in score.reason_codes})),
            run_ids=execution.run_ids,
            event_types=execution.event_types,
            before_files=execution.before_files,
            after_files=execution.after_files,
            metrics=metrics,
        )
        return EvalWorkerResult(
            report=report,
            events=execution.events,
            before_files=execution.before_files,
            after_files=execution.after_files,
        )
    except EvalExecutionError as exc:
        return EvalWorkerResult(error_code=exc.code)
    except IsolationError as exc:
        return EvalWorkerResult(error_code=exc.code)
    except CorpusError as exc:
        return EvalWorkerResult(error_code=exc.code)
    except EvalCodecError as exc:
        return EvalWorkerResult(error_code=exc.code)
    except Exception:
        return EvalWorkerResult(error_code="runtime_exception")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="vera.evals.worker")
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args(argv)
    request_path = Path(args.request)
    result_path = Path(args.result)
    try:
        request = EvalCodec.decode_worker_request(request_path.read_bytes(), source="request.json")
        result = run_worker(request)
        _write_result(result_path, result)
    except Exception:
        if not result_path.exists():
            _write_result(result_path, EvalWorkerResult(error_code="worker_protocol_error"))
        raise SystemExit(1) from None


def _status_from_scores(scores: tuple[EvalScore, ...]) -> EvalStatus:
    gated = [
        score
        for score in scores
        if score.dimension.value in _DECLARED_GATES
        and score.status is not DimensionStatus.NOT_APPLICABLE
    ]
    if any(score.status is DimensionStatus.FAIL for score in gated):
        return EvalStatus.FAIL
    return EvalStatus.PASS


def _write_result(path: Path, result: EvalWorkerResult) -> None:
    if path.exists():
        raise FileExistsError(path)
    payload = result.model_dump_json().encode("utf-8")
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)
    os.chmod(path, 0o600)


if __name__ == "__main__":
    main()
