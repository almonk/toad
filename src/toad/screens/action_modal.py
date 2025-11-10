from textual.app import ComposeResult
from textual import on
from textual import containers
from textual import getters
from textual.screen import ModalScreen
from textual import widgets
from textual.widget import Widget


from toad.widgets.command_pane import CommandPane


class ActionModal(ModalScreen):
    """Executes an action command."""

    command_pane = getters.query_one(CommandPane)
    ok_button = getters.query_one("#ok", widgets.Button)

    BINDINGS = [("escape", "dismiss_modal", "Dismiss")]

    def __init__(
        self,
        title: str,
        command: str,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._title = title
        self._command = command
        super().__init__(name=name, id=id, classes=classes)

    def get_loading_widget(self) -> Widget:
        return widgets.LoadingIndicator()

    def compose(self) -> ComposeResult:
        with containers.VerticalGroup(id="container"):
            yield CommandPane()
            yield widgets.Button("OK", id="ok", disabled=True)

    def enable_button(self) -> None:
        self.ok_button.loading = False
        self.ok_button.disabled = False
        self.ok_button.focus()

    @on(CommandPane.CommandComplete)
    def on_command_complete(self, event: CommandPane.CommandComplete) -> None:
        self.enable_button()

    def on_mount(self) -> None:
        self.ok_button.loading = True
        self.command_pane.border_title = self._title

        def write_command() -> None:
            """Write and execute the command."""
            self.command_pane.anchor()
            self.command_pane.write(f"$ {self._command}\n")
            self.command_pane.execute(self._command)

        self.call_after_refresh(write_command)

    @on(widgets.Button.Pressed)
    def on_button_pressed(self) -> None:
        self.action_dismiss_modal()

    def action_dismiss_modal(self) -> None:
        self.dismiss(self.command_pane.return_code)
