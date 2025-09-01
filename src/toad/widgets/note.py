from typing import Iterable
from textual.widgets import Static

from toad.menus import MenuItem


class Note(Static):
    def get_block_menu(self) -> Iterable[MenuItem]:
        return
        yield

    def get_block_content(self) -> str | None:
        return str(self.render())

    def action_hello(self, message: str) -> None:
        self.notify(message, severity="warning")
