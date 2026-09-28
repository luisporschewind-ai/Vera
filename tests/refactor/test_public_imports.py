"""Characterization tests for the public façade imports before splitting."""

from __future__ import annotations

import inspect

from vera.presentation.projector import (
    AppendBlock,
    FocusBlock,
    TimelineMutation,
    TimelineProjector,
    UpdateBlock,
    project_user_prompt,
)
from vera.runtime.engine import (
    ProposalInput,
    SnapshotPersistError,
    VeraRuntime,
    claims_unissued_changeset,
    tool_call_target,
)
from vera.session.controller import SessionController, SessionSnapshot


def _parameter_names(callable_object: object) -> tuple[str, ...]:
    return tuple(inspect.signature(callable_object).parameters)


def test_public_symbols_remain_importable_from_legacy_modules() -> None:
    assert ProposalInput.__name__ == "ProposalInput"
    assert SnapshotPersistError.__name__ == "SnapshotPersistError"
    assert VeraRuntime.__name__ == "VeraRuntime"
    assert SessionController.__name__ == "SessionController"
    assert SessionSnapshot.__name__ == "SessionSnapshot"
    assert TimelineProjector.__name__ == "TimelineProjector"
    assert AppendBlock.__name__ == "AppendBlock"
    assert UpdateBlock.__name__ == "UpdateBlock"
    assert FocusBlock.__name__ == "FocusBlock"
    assert TimelineMutation is not None
    assert callable(project_user_prompt)
    assert callable(claims_unissued_changeset)
    assert callable(tool_call_target)


def test_public_constructor_and_method_parameter_names_are_stable() -> None:
    assert _parameter_names(VeraRuntime.__init__) == (
        "self",
        "adapter",
        "registry",
        "state_dir",
        "limits",
        "command_policy",
        "snapshot_store",
        "installation_id",
        "artifact_prefix",
        "recovery_coordinator",
        "file_writer",
        "policy_engine",
        "retry_policy",
        "sleep",
        "content_detector",
        "project_instructions",
        "workspace_permissions",
        "access_session",
        "process_supervisor",
    )
    assert _parameter_names(SessionController.__init__) == (
        "self",
        "dependencies",
        "workspace",
        "model_profile",
        "conversation",
        "status_service",
        "runtime_builder",
        "session_store",
        "loaded_session",
        "source",
    )
    assert _parameter_names(TimelineProjector.apply) == ("self", "output")
