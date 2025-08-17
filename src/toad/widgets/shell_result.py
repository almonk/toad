from __future__ import annotations

from textual.app import ComposeResult
from textual import containers
from textual.highlight import highlight
from textual.widgets import Static
from textual import work

from toad.widgets.ansi_log import ANSILog
from toad.widgets.non_selectable_label import NonSelectableLabel
from toad.shell import Shell


class ShellResult(containers.HorizontalGroup):
    def __init__(
        self,
        command: str,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        self._command = command
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)

    def compose(self) -> ComposeResult:
        yield NonSelectableLabel("$", id="prompt")
        yield Static(highlight(self._command, language="sh"))
