"""Terminal widgets for the Vera Textual shell."""

from vera.terminal.widgets.blocks import DiffBlockWidget, TimelineBlockWidget
from vera.terminal.widgets.composer import PromptComposer
from vera.terminal.widgets.header import VeraHeader
from vera.terminal.widgets.status_line import VeraStatusLine
from vera.terminal.widgets.timeline import ConversationTimeline

__all__ = [
    "ConversationTimeline",
    "DiffBlockWidget",
    "PromptComposer",
    "TimelineBlockWidget",
    "VeraHeader",
    "VeraStatusLine",
]
