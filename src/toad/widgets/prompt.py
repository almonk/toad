from dataclasses import dataclass

from pathlib import Path
from typing import Self

from textual import on
from textual.reactive import var
from textual.app import ComposeResult

from textual.actions import SkipAction
from textual.binding import Binding

from textual.content import Content
from textual import getters
from textual.message import Message
from textual.widgets import OptionList, TextArea, Label
from textual import containers
from textual.widget import Widget
from textual.widgets.option_list import Option
from textual.widgets.text_area import Selection
from textual import events

from toad.app import ToadApp
from toad import messages
from toad.widgets.highlighted_textarea import HighlightedTextArea
from toad.widgets.condensed_path import CondensedPath
from toad.widgets.path_search import PathSearch
from toad.widgets.plan import Plan
from toad.widgets.question import Ask, Question
from toad.messages import UserInputSubmitted
from toad.slash_command import SlashCommand
from toad.prompt.extract import extract_paths_from_prompt
from toad.acp.agent import Mode


class AutoCompleteOptions(OptionList, can_focus=False):
    """A list of auto complete options (slash commands)."""

    def watch_highlighted(self, highlighted: int | None) -> None:
        super().watch_highlighted(highlighted)


class ModeSwitcher(OptionList):
    BINDINGS = [Binding("escape", "dismiss")]

    @on(OptionList.OptionSelected)
    def on_option_selected(self, event: OptionList.OptionSelected):
        self.post_message(messages.ChangeMode(event.option_id))
        self.blur()

    def action_dismiss(self):
        self.blur()


class InvokeFileSearch(Message):
    pass


class AgentInfo(Label):
    pass


class ModeInfo(Label):
    pass


class PromptTextArea(HighlightedTextArea):
    BINDING_GROUP_TITLE = "Prompt"

    BINDINGS = [
        Binding(
            "enter",
            "submit",
            "Send",
            key_display="⏎",
            priority=True,
            tooltip="Send the prompt to the agent",
        ),
        Binding(
            "ctrl+j,shift+enter",
            "newline",
            "Line",
            key_display="⇧+⏎",
            tooltip="Insert a new line character",
        ),
        Binding(
            "ctrl+j,shift+enter",
            "multiline_submit",
            "Send",
            key_display="⇧+⏎",
            tooltip="Send the prompt to the agent",
        ),
    ]

    auto_completes: var[list[Option]] = var(list)
    multi_line = var(False, bindings=True)
    shell_mode = var(False, bindings=True)
    agent_ready: var[bool] = var(False)

    class Submitted(Message):
        def __init__(self, markdown: str) -> None:
            self.markdown = markdown
            super().__init__()

    class RequestShellMode(Message):
        pass

    class CancelShell(Message):
        pass

    def on_mount(self) -> None:
        self.highlight_cursor_line = False
        self.hide_suggestion_on_blur = False

    def on_key(self, event: events.Key) -> None:
        if (
            not self.shell_mode
            and self.cursor_location == (0, 0)
            and event.character in {"!", "$"}
        ):
            self.post_message(self.RequestShellMode())
            event.prevent_default()

    def update_suggestion(self) -> None:
        if self.selection.start == self.selection.end and self.text.startswith("/"):
            prompt = self.query_ancestor(Prompt)
            cursor_row, cursor_column = prompt.prompt_text_area.selection.end
            line = prompt.prompt_text_area.document.get_line(cursor_row)
            post_cursor = line[cursor_column:]
            pre_cursor = line[:cursor_column]
            prompt.load_suggestions(pre_cursor, post_cursor)
        else:
            self.query_ancestor(Prompt).show_auto_completes = False

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "newline" and self.multi_line:
            return False
        if action == "submit" and self.multi_line:
            return False
        if action == "multiline_submit":
            return self.multi_line
        return True

    def action_multiline_submit(self) -> None:
        if not self.agent_ready:
            self.app.bell()
            self.post_message(
                messages.Flash(
                    "Agent is not ready. Please wait while the agent conntects…",
                    "warning",
                )
            )
            return
        self.post_message(UserInputSubmitted(self.text, self.shell_mode))
        self.clear()

    def action_newline(self) -> None:
        self.insert("\n")

    def action_submit(self) -> None:
        if not self.agent_ready:
            self.app.bell()
            self.post_message(
                messages.Flash(
                    "Agent is not ready. Please wait while the agent connects…",
                    "warning",
                )
            )
            return
        if self.suggestion:
            self.insert(self.suggestion + " ")
            self.suggestion = ""
            return
        self.post_message(UserInputSubmitted(self.text, self.shell_mode))
        self.clear()

    def action_cursor_up(self, select: bool = False):
        if self.auto_completes:
            self.post_message(Prompt.AutoCompleteMove(-1))
        else:
            if self.selection.is_empty and not select:
                row, _column = self.selection[0]
                if row == 0 or row == (self.wrapped_document.height - 1):
                    self.post_message(
                        messages.HistoryMove(-1, self.shell_mode, self.text)
                    )
                    return
            super().action_cursor_up(select)

    def action_cursor_down(self, select: bool = False):
        if self.auto_completes:
            self.post_message(Prompt.AutoCompleteMove(+1))
        else:
            if self.selection.is_empty and not select:
                row, _column = self.selection[0]
                if row == 0 or row == (self.wrapped_document.height - 1):
                    self.post_message(
                        messages.HistoryMove(+1, self.shell_mode, self.text)
                    )
                    return
            super().action_cursor_down(select)

    def action_delete_left(self) -> None:
        selection = self.selection
        if selection.start == selection.end and self.selection.end == (0, 0):
            self.post_message(self.CancelShell())
            return
        return super().action_delete_left()

    def watch_selection(
        self, previous_selection: Selection, selection: Selection
    ) -> None:
        if selection.start == selection.end:
            previous_y, previous_x = previous_selection.end
            y, x = selection.end
            if y == previous_y:
                direction = -1 if x < previous_x else +1
            else:
                direction = 0
            line = self.document.get_line(y)
            for _path, start, end in extract_paths_from_prompt(line):
                if x > start and x < end:
                    self.selection = Selection((y, start), (y, end))
                    break
                if direction == -1 and x == end:
                    self.selection = Selection((y, start), (y, end))
                    break

            if x > 0 and x <= len(line) and line[x - 1] == "@":
                remaining_line = line[x + 1 :]
                if not remaining_line or remaining_line[0].isspace():
                    self.post_message(InvokeFileSearch())


class Prompt(containers.VerticalGroup):
    BINDINGS = [
        Binding("escape", "dismiss", "Dismiss"),
    ]

    PROMPT_NULL = " "
    PROMPT_SHELL = Content.styled("$", "$text-primary")
    PROMPT_AI = Content.styled("❯", "$text-secondary")
    PROMPT_MULTILINE = Content.styled("☰", "$text-secondary")

    prompt_container = getters.query_one("#prompt-container", Widget)
    prompt_text_area = getters.query_one(PromptTextArea)
    prompt_label = getters.query_one("#prompt", Label)
    current_directory = getters.query_one(CondensedPath)
    path_search = getters.query_one(PathSearch)
    question = getters.query_one(Question)
    auto_complete = getters.query_one(AutoCompleteOptions)
    mode_switcher = getters.query_one(ModeSwitcher)

    auto_completes: var[list[Option]] = var(list)
    show_auto_completes: var[bool] = var(False, bindings=True)
    slash_commands: var[list[SlashCommand]] = var(list)
    shell_mode = var(False)
    multi_line = var(False)
    show_path_search = var(False, toggle_class="-show-path-search")
    project_path = var(Path())
    working_directory = var("")
    agent_info = var(Content(""))
    _ask: var[Ask | None] = var(None)
    plan: var[list[Plan.Entry]]
    agent_ready: var[bool] = var(False)
    current_mode: var[Mode | None] = var(None)
    modes: var[dict[str, Mode] | None] = var(None)

    app = getters.app(ToadApp)

    @dataclass
    class AutoCompleteMove(Message):
        direction: int

    def __init__(
        self,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ):
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self.ask_queue: list[Ask] = []

    @property
    def text(self) -> str:
        return self.prompt_text_area.text

    @text.setter
    def text(self, text: str) -> None:
        self.prompt_text_area.text = text
        self.prompt_text_area.selection = Selection.cursor(
            self.prompt_text_area.get_cursor_line_end_location()
        )

    def watch_current_mode(self, mode: Mode | None) -> None:
        self.set_class(mode is not None, "-has-mode")
        if mode is not None:
            tooltip = Content.from_markup(
                "[b]$description[/]\n\n[dim](click to open mode switcher)",
                description=mode.description,
            )
            self.query_one(ModeInfo).with_tooltip(tooltip).update(mode.name)
        self.watch_modes(self.modes)

    def watch_show_auto_completes(self, show: bool) -> None:
        self.auto_complete.display = show
        if not show:
            self.prompt_text_area.suggestion = ""

    def ask(self, ask: Ask) -> None:
        """Replace the textarea prompt with a menu of options.

        Args:
            ask: An `Ask` instance which contains a question and responses.
        """
        self.ask_queue.append(ask)
        if self._ask is None:
            self._ask = self.ask_queue.pop(0)

    @on(events.Click, "ModeInfo")
    def on_click(self):
        self.mode_switcher.focus()

    def watch_modes(self, modes: dict[str, Mode] | None) -> None:
        from toad.visuals.columns import Columns

        columns = Columns("auto", "auto", "flex")
        if modes is not None:
            mode_list = sorted(modes.values(), key=lambda mode: mode.name.lower())
            for mode in mode_list:
                columns.add_row(
                    (
                        Content.styled("✔", "$text-success")
                        if self.current_mode and mode.id == self.current_mode.id
                        else ""
                    ),
                    Content.from_markup("[bold]$mode[/]", mode=mode.name),
                    Content.styled(mode.description or "", "dim"),
                )
        else:
            mode_list = []

        self.mode_switcher.set_options(
            [Option(row, id=mode.id) for row, mode in zip(columns, mode_list)]
        )
        if self.current_mode is not None:
            self.mode_switcher.highlighted = self.mode_switcher.get_option_index(
                self.current_mode.id
            )

    def watch_agent_ready(self, ready: bool) -> None:
        self.set_class(not ready, "-not-ready")
        if ready:
            self.prompt_text_area.focus()
            self.query_one(AgentInfo).update(self.agent_info)

    def watch_agent_info(self, agent_info: Content) -> None:
        if self.agent_ready:
            self.query_one(AgentInfo).update(agent_info)
        else:
            self.query_one(AgentInfo).update("initializing…")

    def watch_multiline(self) -> None:
        self.update_prompt()

    def watch_shell_mode(self) -> None:
        self.update_prompt()

    # def watch_project_path(self, path: Path) -> None:
    #     pass

    def watch_working_directory(self, working_directory: str) -> None:
        out_of_bounds = not Path(working_directory).is_relative_to(self.project_path)
        if out_of_bounds and not self.has_class("-working-directory-out-of-bounds"):
            self.post_message(
                messages.Flash(
                    "You have navigated away from the project directory",
                    style="error",
                    duration=5,
                )
            )
        self.set_class(
            out_of_bounds,
            "-working-directory-out-of-bounds",
        )

    def watch__ask(self, ask: Ask | None) -> None:
        self.set_class(ask is not None, "-mode-ask")
        if ask is None:
            self.prompt_text_area.focus()
        else:
            self.question.update(ask)
            self.question.focus()

    def update_prompt(self):
        """Update the prompt according to the current mode."""
        if self.shell_mode:
            self.prompt_label.update(self.PROMPT_SHELL, layout=False)
            self.add_class("-shell-mode")
            self.prompt_text_area.placeholder = Content.from_markup(
                "Enter shell command\t[r]▌esc▐[/r] prompt mode"
            ).expand_tabs(8)
            self.prompt_text_area.highlight_language = "shell"
        else:
            self.prompt_label.update(
                self.PROMPT_MULTILINE if self.multi_line else self.PROMPT_AI,
                layout=False,
            )
            self.remove_class("-shell-mode")

            self.prompt_text_area.placeholder = Content.assemble(
                "What would you like to do?\t".expandtabs(8),
                ("▌!▐", "r"),
                " shell ",
                ("▌/▐", "r"),
                " commands ",
                ("▌@▐", "r"),
                " files",
            )
            self.prompt_text_area.highlight_language = "markdown"

    @property
    def likely_shell(self) -> bool:
        text = self.prompt_text_area.text
        if "\n" in text or " " in text:
            return False

        shell_commands = {
            command.strip()
            for command in self.app.settings.get(
                "shell.allow_commands", expect_type=str
            ).split()
        }
        if text.split(" ", 1)[0] in shell_commands:
            return True
        return False

    @property
    def is_shell_mode(self) -> bool:
        return self.shell_mode or self.likely_shell

    def focus(self, scroll_visible: bool = True) -> Self:
        if self._ask is not None:
            self.question.focus()
        else:
            self.query(HighlightedTextArea).focus()
        return self

    def append(self, text: str) -> None:
        self.query_one(HighlightedTextArea).insert(text)

    def watch_auto_completes(self, auto_complete: list[Option]) -> None:
        if auto_complete:
            self.auto_complete.set_options(auto_complete)
            self.auto_complete.action_cursor_down()
            if (
                highlighted_option := self.auto_complete.highlighted_option
            ) is not None and highlighted_option.id:
                self.suggest(highlighted_option.id)
            self.show_auto_completes = True
        else:
            self.auto_complete.clear_options()
            self.show_auto_completes = False

    def watch_show_path_search(self, show: bool) -> None:
        self.prompt_text_area.suggestion = ""

    def set_auto_completes(self, auto_completes: list[Option] | None) -> None:
        self.auto_completes = auto_completes.copy() if auto_completes else []
        if self.auto_completes:
            self.update_auto_complete_location()

    @on(HighlightedTextArea.CursorMove)
    def on_cursor_move(self, event: HighlightedTextArea.CursorMove) -> None:
        selection = event.selection
        if selection.end != selection.start:
            self.show_auto_completes = False
            return

        self.show_auto_completes = (
            self.prompt_text_area.cursor_at_end_of_line or not self.text
        ) and bool(self.auto_completes)

        self.update_auto_complete_location()
        event.stop()

    def update_auto_complete_location(self):
        if self.auto_complete.display:
            cursor_offset = (self.prompt_text_area.cursor_screen_offset) + (-2, 0)
            self.auto_complete.absolute_offset = cursor_offset

    @on(PromptTextArea.RequestShellMode)
    def on_request_shell_mode(self, event: PromptTextArea.RequestShellMode):
        self.shell_mode = True
        self.update_prompt()

    @on(TextArea.Changed)
    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        text = event.text_area.text

        self.multi_line = "\n" in text or "```" in text

        if not self.multi_line and self.likely_shell:
            self.shell_mode = True

        self.update_prompt()
        cursor_row, cursor_column = self.prompt_text_area.selection.end
        line = self.prompt_text_area.document.get_line(cursor_row)
        post_cursor = line[cursor_column:]
        pre_cursor = line[:cursor_column]
        self.load_suggestions(pre_cursor, post_cursor)

    @on(AutoCompleteMove)
    def on_auto_complete_move(self, event: AutoCompleteMove) -> None:
        if self.auto_complete.display:
            if event.direction == -1:
                self.auto_complete.action_cursor_up()
            else:
                self.auto_complete.action_cursor_down()

    @on(PromptTextArea.CancelShell)
    def on_cancel_shell(self, event: PromptTextArea.CancelShell):
        self.shell_mode = False

    @on(InvokeFileSearch)
    def on_invoke_file_search(self, event: InvokeFileSearch) -> None:
        event.stop()
        self.show_path_search = True
        self.path_search.load_paths()

    @on(messages.PromptSuggestion)
    def on_prompt_suggestion(self, event: messages.PromptSuggestion) -> None:
        event.stop()
        self.prompt_text_area.suggestion = event.suggestion

    @on(messages.Dismiss)
    def on_dismiss(self, event: messages.Dismiss) -> None:
        event.stop()
        if event.widget is self.path_search:
            self.show_path_search = False
            self.focus()

    @on(messages.InsertPath)
    def on_insert_path(self, event: messages.InsertPath) -> None:
        event.stop()
        if " " in event.path:
            path = f'"{event.path}"'
        else:
            path = event.path
            if (
                self.prompt_text_area.get_text_range(*self.prompt_text_area.selection)
                != " "
            ):
                path += " "
        self.prompt_text_area.insert(path)

    @on(Question.Answer)
    def on_question_answer(self, event: Question.Answer) -> None:
        """Question has been answered."""
        event.stop()

        def remove_question() -> None:
            """Remove the question and restore the text prompt."""
            if self.ask_queue:
                self._ask = self.ask_queue.pop(0)
            else:
                self._ask = None

        if self._ask is not None and (callback := self._ask.callback) is not None:
            callback(event.answer)

        self.set_timer(0.3, remove_question)

    def suggest(self, suggestion: str) -> None:
        if suggestion.startswith(self.text) and self.text != suggestion:
            self.prompt_text_area.suggestion = suggestion[len(self.text) :]

    def load_suggestions(self, pre_cursor: str, post_cursor: str) -> None:
        if post_cursor.strip():
            self.set_auto_completes(None)
            return
        pre_cursor = pre_cursor.casefold()
        post_cursor = post_cursor.casefold()
        suggestions: list[Option] = []

        if not pre_cursor:
            self.set_auto_completes(None)
            return

        from toad.visuals.columns import Columns

        columns = Columns("auto", "flex")

        if not self.is_shell_mode:
            for slash_command in self.slash_commands:
                if str(slash_command).startswith(pre_cursor) and pre_cursor != str(
                    slash_command
                ):
                    row = columns.add_row(
                        Content.styled(slash_command.command, "$text-success"),
                        Content.styled(slash_command.help, "dim"),
                    )
                    suggestions.append(
                        Option(
                            row,
                            id=slash_command.command,
                        )
                    )

        self.set_auto_completes(suggestions)

    @on(events.DescendantBlur, "PromptTextArea")
    def on_descendant_blur(self, event: events.DescendantBlur) -> None:
        self.auto_complete.visible = False

    @on(events.DescendantFocus, "PromptTextArea")
    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        self.auto_complete.visible = True

    def compose(self) -> ComposeResult:
        yield AutoCompleteOptions()
        yield PathSearch().data_bind(root=Prompt.project_path)

        with containers.HorizontalGroup(id="prompt-container"):
            yield Question()
            with containers.HorizontalGroup(id="text-prompt"):
                yield Label(self.PROMPT_AI, id="prompt")
                yield PromptTextArea().data_bind(
                    auto_completes=Prompt.auto_completes,
                    multi_line=Prompt.multi_line,
                    shell_mode=Prompt.shell_mode,
                    agent_ready=Prompt.agent_ready,
                )

        with containers.HorizontalGroup(id="info-container"):
            yield AgentInfo()
            yield CondensedPath().data_bind(path=Prompt.working_directory)
            yield ModeSwitcher()
            yield ModeInfo("mode")

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "dismiss":
            return True if (self.shell_mode or self.show_auto_completes) else False
        return True

    def action_dismiss(self) -> None:
        if self.shell_mode:
            self.shell_mode = False
        elif self.show_auto_completes:
            self.show_auto_completes = False
        else:
            raise SkipAction()
