"""Import contracts for Runtime's tool, verification, and approval flows."""

from vera.runtime.approval_flow import ApprovalFlow
from vera.runtime.tool_flow import ToolExecutionFlow
from vera.runtime.verification_flow import VerificationFlow


def test_extracted_runtime_flow_facades_are_available() -> None:
    assert ApprovalFlow is not None
    assert ToolExecutionFlow is not None
    assert VerificationFlow is not None
    assert callable(ToolExecutionFlow.execute_prepared)
    assert callable(VerificationFlow.verify)
    assert callable(ApprovalFlow.resolve)
