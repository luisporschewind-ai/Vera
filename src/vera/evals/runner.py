"""Run isolated evaluation cases through Worker subprocesses."""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from uuid import uuid4

from vera.evals.contracts import (
    DimensionStatus,
    EvalDimension,
    EvalReport,
    EvalScore,
    EvalStatus,
    EvalSuiteReport,
    EvalWorkerRequest,
)
from vera.evals.corpus import CorpusLoader
from vera.evals.evidence import EvidenceWriter
from vera.evals.isolation import FixtureIsolator
from vera.evals.process_runner import CaseProcessRunner

CaseRunner = Callable[[str, Path | None], EvalReport]


class EvalSuiteRunner:
    def __init__(
        self,
        corpus_root: Path | None = None,
        *,
        case_runner: CaseRunner | None = None,
        process_runner: CaseProcessRunner | None = None,
        isolator_root: Path | None = None,
    ) -> None:
        self.loader = CorpusLoader(corpus_root)
        self.process_runner = process_runner or CaseProcessRunner()
        self.isolator_root = isolator_root
        self._case_runner = case_runner
        self._evidence = EvidenceWriter()

    def run_case(self, case_id: str, output_root: Path | None = None) -> EvalReport:
        if self._case_runner is not None:
            return self._case_runner(case_id, output_root)
        evaluation_id = f"eval-{uuid4().hex}"
        loaded = self.loader.load(case_id)
        temp_root = Path(self.isolator_root or tempfile.mkdtemp(prefix="vera-eval-suite-"))
        isolated = FixtureIsolator(temp_root).prepare(loaded)
        try:
            request = EvalWorkerRequest(
                evaluation_id=evaluation_id,
                case_id=case_id,
                corpus_root=loaded.corpus_root,
                workspace=isolated.workspace,
                state_dir=isolated.state_dir,
                staging_dir=isolated.staging_dir,
            )
            result = self.process_runner.run(request, loaded.case.timeout_seconds)
            report = result.report or _synthetic_report(evaluation_id, case_id, result.error_code)
            if result.report is None:
                from vera.evals.contracts import EvalWorkerResult

                result = EvalWorkerResult(
                    error_code=result.error_code,
                    report=report,
                    events=result.events,
                    before_files=result.before_files,
                    after_files=result.after_files,
                )
            if output_root is not None:
                self._evidence.publish(result, output_root)
            return report
        finally:
            isolated.cleanup()

    def run_suite(
        self, case_ids: Sequence[str], output_root: Path | None = None
    ) -> EvalSuiteReport:
        reports = [self.run_case(case_id, output_root) for case_id in case_ids]
        suite_id = f"suite-{uuid4().hex}"
        status = EvalStatus.PASS
        if any(item.status is not EvalStatus.PASS for item in reports):
            status = EvalStatus.FAIL
        suite = EvalSuiteReport(evaluation_id=suite_id, status=status, cases=tuple(reports))
        if output_root is not None:
            from vera.evals.codec import EvalCodec

            payload = EvalCodec.encode_suite_report(suite).encode("utf-8")
            target = output_root / "suite-report.json"
            if target.exists():
                raise FileExistsError(target)
            target.write_bytes(payload)
            target.chmod(0o600)
        return suite


def _synthetic_report(evaluation_id: str, case_id: str, error_code: str | None) -> EvalReport:
    code = error_code or "worker_protocol_error"
    status = EvalStatus.TIMEOUT if code == "case_timeout" else EvalStatus.ERROR
    return EvalReport(
        evaluation_id=evaluation_id,
        case_id=case_id,
        status=status,
        scores=(
            EvalScore(
                dimension=EvalDimension.CORRECTNESS,
                status=DimensionStatus.FAIL,
                reason_codes=(code,),
            ),
        ),
        reason_codes=(code,),
    )
