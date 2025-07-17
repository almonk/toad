from textual.app import App, ComposeResult
from textual.screen import Screen

from toad.main_screen import MainScreen


class ToadApp(App):
    CSS_PATH = "toad.tcss"

    def on_mount(self) -> None:
        self.theme = "dracula"

    def get_default_screen(self) -> Screen:
        return MainScreen()
