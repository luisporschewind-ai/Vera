"""Plain-mode session driver facade over InteractiveSession/SessionController."""

from __future__ import annotations

from pathlib import Path

from vera.bootstrap import RuntimeBuilder, RuntimeDependencies
from vera.cli_session import InteractiveSession, SessionIO
from vera.session.controller import SessionController
from vera.session.conversation import ConversationContext
from vera.session.status import SessionStatusService


class PlainSessionDriver:
    """Human line-oriented driver without alternate screen or animations."""

    def __init__(
        self,
        dependencies: RuntimeDependencies,
        workspace: Path,
        model_profile: str,
        io: SessionIO,
        *,
        conversation: ConversationContext | None = None,
        status_service: SessionStatusService | None = None,
        runtime_builder: RuntimeBuilder | None = None,
        controller: SessionController | None = None,
    ) -> None:
        self.session = InteractiveSession(
            dependencies,
            workspace,
            model_profile,
            io,
            conversation=conversation,
            status_service=status_service,
            runtime_builder=runtime_builder,
            controller=controller,
        )

    def run(self) -> int:
        return self.session.run()
