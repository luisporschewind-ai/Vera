"""External-editor interaction flow for sessions."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from vera.contracts.streaming import RuntimeOutput
from vera.session.external_editor import ExternalEditor, ExternalEditorError

if TYPE_CHECKING:
    from vera.session.controller import SessionController


def confirm_editor(host: SessionController, accept: bool) -> Iterator[RuntimeOutput]:
    host._editor_confirmed = accept
    yield host._session_event(
        "session.editor_confirmed" if accept else "session.editor_declined",
        {"accepted": accept},
    )


def open_editor(host: SessionController, text: str) -> Iterator[RuntimeOutput]:
    argv = tuple(getattr(host.dependencies.config, "editor_argv", ()) or ())
    try:
        editor = ExternalEditor(argv, host.dependencies.config.state_dir / "drafts")
    except ExternalEditorError as exc:
        yield host._session_event(
            "session.action_rejected",
            {"reason_code": exc.code, "message": str(exc)},
        )
        return
    preview = editor.preview()
    if not host._editor_confirmed:
        yield host._session_event(
            "session.editor_preview",
            {"argv": list(preview), "needs_confirmation": True},
        )
        return
    path = editor.write_draft(text)
    host._editor_draft = path
    try:
        result = editor.run(path)
    except ExternalEditorError as exc:
        editor.cleanup(path)
        host._editor_draft = None
        yield host._session_event(
            "session.action_rejected",
            {"reason_code": exc.code, "message": str(exc)},
        )
        return
    editor.cleanup(path)
    host._editor_draft = None
    yield host._session_event(
        "session.editor_closed",
        {"status": result.status, "changed": result.changed, "text": result.text},
    )


class SessionEditorFlow:
    """Stable façade for editor confirmation and draft lifecycle."""

    confirm_editor = staticmethod(confirm_editor)
    open_editor = staticmethod(open_editor)
