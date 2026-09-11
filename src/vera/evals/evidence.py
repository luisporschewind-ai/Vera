"""Atomically publish private evaluation evidence without file bodies."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import NoReturn

from vera.evals.codec import EvalCodec
from vera.evals.contracts import EvalWorkerResult


class EvidenceError(ValueError):
    def __init__(self, code: str, path: Path | str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.path = Path(path)
        self.message = message


def _fail(code: str, path: Path | str, message: str) -> NoReturn:
    raise EvidenceError(code, path, message)


class EvidenceWriter:
    def publish(self, result: EvalWorkerResult, output_root: Path) -> Path:
        if result.report is None:
            _fail("missing_report", output_root, "cannot publish evidence without a report")
        evaluation_id = result.report.evaluation_id
        destination = output_root / evaluation_id
        if destination.exists():
            _fail("output_exists", destination, "evaluation output directory already exists")
        output_root.mkdir(parents=True, exist_ok=True)
        os.chmod(output_root, 0o700)
        staging = Path(tempfile.mkdtemp(prefix="vera-eval-evidence-", dir=output_root))
        try:
            os.chmod(staging, 0o700)
            encoded = EvalCodec.encode_report(result.report).encode("utf-8")
            _write_private(staging / "report.json", encoded)
            files_payload = {
                "before_files": [item.model_dump(mode="json") for item in result.before_files],
                "after_files": [item.model_dump(mode="json") for item in result.after_files],
            }
            _write_private(
                staging / "files.json",
                json.dumps(files_payload, ensure_ascii=False, sort_keys=True).encode("utf-8"),
            )
            lines = [event.model_dump_json() for event in result.events]
            body = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
            _write_private(staging / "events.jsonl", body)
            os.replace(staging, destination)
            os.chmod(destination, 0o700)
        except Exception:
            if staging.exists() and staging.parent == output_root:
                shutil.rmtree(staging, ignore_errors=True)
            raise
        return destination


def _write_private(path: Path, payload: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, 0o600)
