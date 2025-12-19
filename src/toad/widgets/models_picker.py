"""Widget for picking a model from pool agents list."""

import asyncio
from dataclasses import dataclass
from operator import itemgetter
from typing import Iterable, Self, Sequence

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.content import Content, Span

from textual import getters
from textual.message import Message
from textual.reactive import var
from textual import containers
from textual import widgets
from textual.widgets.option_list import Option

from toad.fuzzy import FuzzySearch
from toad.messages import Dismiss
from toad.visuals.columns import Columns


class ModelsPicker(containers.VerticalGroup):
    """A widget to pick models from pool agents list."""

    CURSOR_BINDING_GROUP = Binding.Group(description="Select")
    BINDINGS = [
        Binding(
            "up",
            "cursor_up",
            "Cursor up",
            group=CURSOR_BINDING_GROUP,
            priority=True,
        ),
        Binding(
            "down",
            "cursor_down",
            "Cursor down",
            group=CURSOR_BINDING_GROUP,
            priority=True,
        ),
        Binding("enter", "submit", "Select model", priority=True),
        Binding("escape", "dismiss", "Dismiss", priority=True),
    ]

    DEFAULT_CSS = """
    ModelsPicker {
        OptionList {
            height: auto;
        }
    }
    """

    input = getters.query_one(widgets.Input)
    option_list = getters.query_one(widgets.OptionList)

    models: var[list[str]] = var(list)

    @dataclass
    class ModelSelected(Message):
        """Posted when a model is selected."""

        model: str

    def __init__(
        self,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self.models = []
        self.fuzzy_search = FuzzySearch(case_sensitive=False)
        self._loading = False

    def compose(self) -> ComposeResult:
        yield widgets.Input(compact=True, placeholder="fuzzy search models")
        yield widgets.OptionList()

    def focus(self, scroll_visible: bool = False) -> Self:
        self.filter_models("")
        self.input.focus(scroll_visible)
        return self

    def on_mount(self) -> None:
        self.filter_models("")

    def on_descendant_blur(self) -> None:
        self.post_message(Dismiss(self))

    @on(widgets.Input.Changed)
    def on_input_changed(self, event: widgets.Input.Changed) -> None:
        event.stop()
        self.filter_models(event.value)

    async def watch_models(self) -> None:
        self.filter_models(self.input.value)

    async def load_models(self) -> None:
        """Load models from pool agents list command."""
        if self._loading:
            return
        self._loading = True

        try:
            proc = await asyncio.create_subprocess_exec(
                "pool",
                "agents",
                "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _stderr = await proc.communicate()

            if proc.returncode == 0 and stdout:
                output = stdout.decode("utf-8").strip()
                # Parse the output - each line is a model name
                models = [
                    line.strip()
                    for line in output.split("\n")
                    if line.strip()
                ]
                self.models = models
        except Exception:
            # If the command fails, show empty list
            self.models = []
        finally:
            self._loading = False

    def filter_models(self, prompt: str) -> None:
        """Filter models by the given prompt.

        Args:
            prompt: Text prompt.
        """
        prompt = prompt.casefold()
        columns = self.columns = Columns("auto")

        models = sorted(self.models, key=str.casefold)
        self.fuzzy_search.cache.grow(len(models))

        if prompt:
            scores: list[tuple[float, Sequence[int], str]] = [
                (
                    *self.fuzzy_search.match(prompt, model),
                    model,
                )
                for model in models
            ]

            scores = sorted(
                [
                    (
                        (
                            score * 2
                            if model.casefold().startswith(prompt)
                            else score
                        ),
                        highlights,
                        model,
                    )
                    for score, highlights, model in scores
                    if score
                ],
                key=itemgetter(0),
                reverse=True,
            )
        else:
            scores = [(1.0, [], model) for model in models]

        def make_row(
            model: str, indices: Iterable[int]
        ) -> tuple[Content, ...]:
            """Make a row for the Columns display.

            Args:
                model: The model name.
                indices: Indices of matching characters.

            Returns:
                A tuple of `Content` instances for use as a column row.
            """
            content = Content.styled(model, "$text-success")
            content = content.add_spans(
                [Span(index, index + 1, "underline not dim") for index in indices]
            )
            return (content,)

        rows = [
            (
                columns.add_row(*make_row(model, indices)),
                model,
            )
            for _, indices, model in scores
        ]
        self.option_list.set_options(
            Option(row, id=model_name) for row, model_name in rows
        )
        if self.display:
            self.option_list.highlighted = 0
        else:
            with self.option_list.prevent(widgets.OptionList.OptionHighlighted):
                self.option_list.highlighted = 0

    def action_cursor_down(self) -> None:
        self.option_list.action_cursor_down()

    def action_cursor_up(self) -> None:
        self.option_list.action_cursor_up()

    def action_dismiss(self) -> None:
        self.post_message(Dismiss(self))

    def action_submit(self) -> None:
        if (option := self.option_list.highlighted_option) is not None:
            with self.input.prevent(widgets.Input.Changed):
                self.input.clear()
            self.post_message(Dismiss(self))
            self.post_message(self.ModelSelected(option.id or ""))


if __name__ == "__main__":
    from textual.app import App, ComposeResult

    class ModelsApp(App):
        def compose(self) -> ComposeResult:
            picker = ModelsPicker()
            picker.models = ["model_a", "model_b", "laguna_agent_1120"]
            yield picker

    ModelsApp().run()
