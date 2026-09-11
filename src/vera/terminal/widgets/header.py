"""Header strip for model, workspace, and session context."""

from __future__ import annotations

from textual.widgets import Static


class VeraHeader(Static):
    """Top status strip; secondary fields hide under 80 columns."""

    DEFAULT_CSS = """
    VeraHeader {
        width: 100%;
    }
    """

    def __init__(
        self,
        *,
        model_profile: str = "default",
        workspace_label: str = ".",
        id: str | None = None,
    ) -> None:
        self._model_profile = model_profile
        self._workspace_label = workspace_label
        super().__init__(f"Vera · {model_profile} · {workspace_label}", id=id)

    def set_narrow(self, narrow: bool) -> None:
        self.set_class(narrow, "-narrow")
        if narrow:
            self.update(f"Vera · {self._model_profile}")
        else:
            self.update(f"Vera · {self._model_profile} · {self._workspace_label}")
