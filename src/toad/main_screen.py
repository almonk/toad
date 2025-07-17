from textual import on
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static
from textual.reactive import var
from textual import getters

from toad.widgets.throbber import Throbber
from toad.widgets.conversation import Conversation


class MainScreen(Screen):
    busy_count = var(0)
    throbber: getters.query_one[Throbber] = getters.query_one("#throbber")

    def compose(self) -> ComposeResult:
        yield Conversation()
