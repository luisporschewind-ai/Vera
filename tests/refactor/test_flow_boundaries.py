"""Import-level contract tests for the first Runtime flow extraction."""

from vera.runtime.content_flow import (
    append_conversation_message,
    prepare_content,
    seed_context,
    seed_project_instructions,
)
from vera.runtime.flow_protocols import ContentFlowHost
from vera.runtime.intake import (
    ProposalInput,
    SnapshotPersistError,
    claims_unissued_changeset,
    tool_call_target,
)


def test_content_flow_exports_are_small_host_boundaries() -> None:
    assert callable(prepare_content)
    assert callable(seed_context)
    assert callable(seed_project_instructions)
    assert callable(append_conversation_message)
    assert ContentFlowHost is not None


def test_intake_symbols_are_defined_in_the_extracted_module() -> None:
    assert ProposalInput.__module__ == "vera.runtime.intake"
    assert SnapshotPersistError.__module__ == "vera.runtime.intake"
    assert claims_unissued_changeset.__module__ == "vera.runtime.intake"
    assert tool_call_target.__module__ == "vera.runtime.intake"
