from vera.session.actions import (
    CancelActiveRun,
    CloseSession,
    ExecuteSlashCommand,
    ResolveSessionApproval,
    SubmitPrompt,
)


def test_action_types_are_stable() -> None:
    assert SubmitPrompt(text="hello").type == "prompt.submit"
    assert ExecuteSlashCommand(raw="/help").type == "session.command"
    assert ResolveSessionApproval(approval_id="a1", decision="approve").type == "approval.resolve"
    assert CancelActiveRun(run_id="run_1").type == "run.cancel"
    assert CloseSession().type == "session.close"
