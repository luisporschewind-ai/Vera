from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from vera.cli_presenter import HumanPresenter
from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import StreamFrame, StreamFrameType
from vera.evals.contracts import (
    DimensionStatus,
    EvalMetrics,
    EvalReport,
    EvalScore,
    EvalStatus,
    EvalWorkerResult,
    FileFact,
)
from vera.evals.evidence import EvidenceWriter
from vera.persistence.journal import EventJournal
from vera.presentation.projector import TimelineProjector
from vera.redaction import DEFAULT_SECRET_POLICY, Redactor, SecretPolicy

SECRET = "sk-live-fixture-secret-9f3a2b1c"
HASH = "a" * 64
RUN_ID = "run_123e4567-e89b-12d3-a456-426614174000"
HIGH_ENTROPY = "QWxhZGRpbjpvcGVuIHNlc2FtZQ=="


def malicious_payload() -> dict[str, object]:
    return {
        "authorization": f"Bearer {SECRET}",
        "api_key": SECRET,
        "message": f"Authorization: Bearer {SECRET}",
        "url": f"https://api.example.test/v1?api_key={SECRET}&q=ok",
        "env": f"DEEPSEEK_API_KEY={SECRET}",
        "error": f"provider rejected {SECRET}",
        "stdout": f"OPENAI_API_KEY={SECRET}",
        "hash": HASH,
        "run_id": RUN_ID,
        "note": "the secret sauce is pepper",
        "entropy": HIGH_ENTROPY,
    }


def _event(payload: dict[str, object]) -> EventEnvelope:
    return EventEnvelope(
        event_id="event-1",
        run_id=RUN_ID,
        sequence=1,
        timestamp=datetime(2026, 9, 12, tzinfo=UTC),
        type="verification.completed",
        payload=payload,  # type: ignore[arg-type]
    )


def _assert_secret_absent(text: str) -> None:
    assert SECRET not in text
    assert f"Bearer {SECRET}" not in text
    assert f"DEEPSEEK_API_KEY={SECRET}" not in text


def test_secret_policy_redacts_structured_and_text_contexts() -> None:
    policy = SecretPolicy()
    payload = Redactor().redact(malicious_payload())
    assert payload["authorization"] == "[REDACTED]"
    assert payload["api_key"] == "[REDACTED]"
    _assert_secret_absent(str(payload))
    assert payload["hash"] == HASH
    assert payload["run_id"] == RUN_ID
    assert payload["note"] == "the secret sauce is pepper"
    assert payload["entropy"] == HIGH_ENTROPY
    assert "ok" in str(payload["url"])
    assert policy.contains_secret(f"Authorization: Bearer {SECRET}")
    assert not policy.contains_secret("the secret sauce is pepper")
    assert not policy.contains_secret(HASH)
    assert not policy.contains_secret(RUN_ID)


def test_high_entropy_is_only_redacted_in_credential_context() -> None:
    redactor = Redactor()
    assert HIGH_ENTROPY in redactor.redact(f"debug={HIGH_ENTROPY}")
    assert HIGH_ENTROPY not in redactor.redact(f"Authorization: Bearer {HIGH_ENTROPY}")
    assert HIGH_ENTROPY not in redactor.redact(f"https://x.test/?token={HIGH_ENTROPY}")


def test_all_outlets_drop_the_same_malicious_fixture(tmp_path: Path) -> None:
    payload = malicious_payload()
    event = _event(payload)
    redactor = Redactor()

    plain: list[str] = []
    HumanPresenter(plain.append, redactor).write_events((event,))
    json_text = redactor.redact_event(event).model_dump_json()
    journal = EventJournal(tmp_path / "state", RUN_ID, redactor)
    journal.append("verification.completed", payload)
    journal_text = (tmp_path / "state" / "runs" / RUN_ID / "events.jsonl").read_text(
        encoding="utf-8"
    )
    projector = TimelineProjector()
    projector.apply(event)
    tui_text = "\n".join(f"{block.title}\n{block.body}" for block in projector.blocks())
    stream = redactor.redact_output(
        StreamFrame(
            run_id=RUN_ID,
            stream_id="s1",
            index=0,
            type=StreamFrameType.ASSISTANT_DELTA,
            payload={"text": f"use {SECRET}"},
        )
    )
    report = EvalReport(
        evaluation_id="eval-secret",
        case_id="plain-answer",
        status=EvalStatus.FAIL,
        scores=(EvalScore(dimension="safety", status=DimensionStatus.FAIL),),
        metrics=EvalMetrics(),
    )
    published = EvidenceWriter(redactor=redactor).publish(
        EvalWorkerResult(
            report=report,
            events=(event,),
            after_files=(FileFact(path="README.md", kind="file", size=8, sha256=HASH),),
        ),
        tmp_path / "evidence",
    )
    evidence_text = (published / "events.jsonl").read_text(encoding="utf-8")
    report_text = (published / "report.json").read_text(encoding="utf-8")

    for text in (
        "\n".join(plain),
        json_text,
        journal_text,
        tui_text,
        str(stream.payload),
        evidence_text,
        report_text,
        str(redactor.redact(ValueError(f"Authorization: Bearer {SECRET}"))),
    ):
        _assert_secret_absent(text)

    assert HASH in journal_text
    assert RUN_ID in journal_text
    assert DEFAULT_SECRET_POLICY.is_forbidden_env_name("OPENAI_API_KEY")
