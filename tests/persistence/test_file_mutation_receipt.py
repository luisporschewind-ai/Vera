from datetime import UTC, datetime

import pytest

from vera.persistence.errors import PersistenceFault
from vera.persistence.operation_receipt import OperationReceipt, OperationReceiptStore


def test_file_mutation_receipt_round_trips_and_is_idempotent(tmp_path) -> None:
    store = OperationReceiptStore(tmp_path)
    receipt = OperationReceipt(
        operation_id="file_mutation_123",
        operation="file_mutation",
        run_id="run-1",
        input_hash="a" * 64,
        terminal_result="file_mutation.applied",
        created_at=datetime.now(UTC),
    )

    store.save(receipt)
    store.save(receipt)

    assert store.load("run-1", "file_mutation_123") == receipt


def test_unknown_receipt_version_is_rejected(tmp_path) -> None:
    store = OperationReceiptStore(tmp_path)
    path = store.path_for("run-1", "file_mutation_123")
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"receipt_version":2,"operation_id":"file_mutation_123",'
        '"operation":"file_mutation","run_id":"run-1",'
        '"input_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
        '"terminal_result":"file_mutation.applied",'
        '"created_at":"2026-09-19T00:00:00Z"}',
        encoding="utf-8",
    )

    with pytest.raises(PersistenceFault):
        store.load("run-1", "file_mutation_123")
