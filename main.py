from __future__ import annotations

import asyncio
from random import randint
from time import monotonic
from pathlib import Path
import os

from rich.segment import Segment
from rich.style import Style as RichStyle
from rich.syntax import Syntax

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.reactive import var
from textual import events
from textual.message import Message
from textual.color import Color, Gradient
from textual.css.styles import RulesMap
from textual.selection import Selection
from textual.strip import Strip
from textual.style import Style
from textual.widget import Widget
from textual.widgets import (
    Markdown,
    TextArea,
    Label,
    Static,
    DirectoryTree,
    TabbedContent,
    TabPane,
)
from textual.visual import Visual
from textual import containers

ASCII_TOAD = r"""
         _   _
        (.)_(.)
     _ (   _   ) _
    / \/`-----'\/ \
  __\ ( (     ) ) /__
  )   /\ \._./ /\   (
   )_/ /|\   /|\ \_(
"""

COLORS = [
    "#881177",
    "#aa3355",
    "#cc6666",
    "#ee9944",
    "#eedd00",
    "#99dd55",
    "#44dd88",
    "#22ccbb",
    "#00bbcc",
    "#0099cc",
    "#3366bb",
    "#663399",
]


WELCOME_MD = """\
## Toad v1.0

Welcome, **Will**!

I am your friendly batrachian coding assistant.

I can help you plan, analyze, debug and write code.
To get started, talk to me in plain English and I will do my best to help!


| command | Explanation |
| --- | --- |
| `/edit` <PATH> | Edit the file at the given path. |
| `/tree` | Show all the files in the current working directory in a tree. |
| `/shell` | Drop in to the shell. |
"""

OUTPUT_MD = """\
I have created two files to implement a calculator application in the Textual library for Python.

let me know if you would like to make any edits.
"""


class Editor(containers.Horizontal):
    DEFAULT_CSS = """
    Editor {
        display: none;
        width: 1fr;
        border-right: thick black 20%;
        TextArea {
            padding: 0 !important;
            margin: 0 !important;
            border: none;
            &:focus {
                border: none;
            }
        }
    }
    """

    tab_index = var(1)

    def compose(self) -> ComposeResult:
        yield TabbedContent()

    async def open_file(self, path: Path) -> None:
        tabbed_content = self.query_one(TabbedContent)
        new_pane = TabPane(
            path.name,
            TextArea.code_editor(
                path.read_text(),
                theme="dracula",
                language="python" if path.name.endswith(".py") else "css",
                highlight_cursor_line=True,
            ),
        )
        self.tab_index += 1
        self.display = True
        await tabbed_content.add_pane(new_pane)

        tabbed_content.active = new_pane.id


class ThrobberVisual(Visual):
    """A Textual 'Visual' object.

    Analogous to a Rich renderable, but with support for transparency.

    """

    gradient = Gradient.from_colors(*[Color.parse(color) for color in COLORS])

    def render_strips(
        self,
        rules: RulesMap,
        width: int,
        height: int | None,
        style: Style,
        selection: Selection | None = None,
        selection_style: Style | None = None,
        post_style: Style | None = None,
    ) -> list[Strip]:
        """Render the Visual into an iterable of strips.

        Args:
            rules: A mapping of style rules, such as the Widgets `styles` object.
            width: Width of desired render.
            height: Height of desired render or `None` for any height.
            style: The base style to render on top of.
            selection: Selection information, if applicable, otherwise `None`.
            selection_style: Selection style if `selection` is not `None`.
            post_style: Optional style to apply post render.

        Returns:
            An list of Strips.
        """

        time = monotonic()
        gradient = self.gradient
        strips = [
            Strip(
                [
                    Segment(
                        "━",
                        RichStyle.from_color(
                            gradient.get_rich_color((offset / width - time) % 1.0)
                        ),
                    )
                    for offset in range(width)
                ],
                width,
            )
        ]
        return strips

    def get_optimal_width(self, rules: RulesMap, container_width: int) -> int:
        return container_width

    def get_height(self, rules: RulesMap, width: int) -> int:
        return 1


class Throbber(Widget):
    DEFAULT_CSS = """
    Throbber {
        width: 100%;
        height: 1;
    }
    """

    show = var(False)

    def watch_show(self, show=False) -> None:
        self.visible = show

    def on_mount(self) -> None:
        self.auto_refresh = 1 / 15

    def render(self) -> ThrobberVisual:
        return ThrobberVisual()


class ResponseWaiter(containers.VerticalGroup):
    DEFAULT_CSS = """
    ResponseWaiter {
        padding-top: 1;
    }
    
    """
    token_count = var(0)

    def on_mount(self) -> None:
        def update_token_count() -> None:
            self.token_count += randint(7, 21)

        self.set_interval(0.05, update_token_count)

    def watch_token_count(self) -> None:
        message = f" [dim]🐸  Talking to toad… [b]{self.token_count}[/b] tokens"
        self.query_one("#message", Static).update(message)

    def compose(self) -> ComposeResult:
        yield Static("...", id="message")


class MarkdownTextArea(TextArea):
    BINDINGS = [Binding("ctrl+j", "submit", "Submit markdown")]

    class Submitted(Message):
        def __init__(self, markdown: str) -> None:
            self.markdown = markdown
            super().__init__()

    def on_mount(self) -> None:
        self.highlight_cursor_line = False

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.post_message(self.Submitted(self.text))
            self.clear()

    def action_submit(self) -> None:
        self.insert("\n")


class CodeOutput(containers.VerticalGroup):
    DEFAULT_CSS = """
    CodeOutput {
        TextArea {
            height: 10;                        
            &.-maximized {
                height: 1fr;
                margin: 1 2;
            }
        }        
        
        Label {
            padding: 1 0 0 1;
            color: $success;
        }

        Markdown {
            padding: 1 0 1 1;
        }
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("calculator.py")
        yield TextArea.code_editor(
            Path("./project/calculator.py").read_text(),
            language="python",
            theme="dracula",
            read_only=True,
            show_cursor=False,
            highlight_cursor_line=False,
        )
        yield Label("calculator.tcss")
        yield TextArea.code_editor(
            Path("./project/calculator.tcss").read_text(),
            language="python",
            theme="dracula",
            read_only=True,
            show_cursor=False,
            highlight_cursor_line=False,
        )
        yield Markdown(OUTPUT_MD)


class Conversation(Widget, can_focus=False, can_focus_children=True):
    DEFAULT_CSS = """
    Conversation {
        # Throbber {
        #     dock: top;
        # }
        width: 1fr;
        TextArea#user {
            dock: bottom;
            min-height: 1;
            max-height: 50%;
            height: auto;
            margin-top: 1;
        }
        Markdown.user-input { 
            background: white 5%;
            margin-left: 1;
            padding-top: 1;
            padding-left: 1;
            border-left: vkey $success 100%;
            text-opacity: 0.8;
            MarkdownBlock:last-child {
                
            }                        
        }
        DirectoryTree {
            margin: 1 0;
            margin-right: 1;
            height: auto;
            max-height: 50%;
        }

        .code-panel {
            max-height: 10;            
        }



    }

    """

    def compose(self) -> ComposeResult:
        yield containers.VerticalScroll(id="contents")
        yield MarkdownTextArea(id="user", highlight_cursor_line=False)

    def on_mount(self) -> None:
        self.query_one("#contents").anchor()

    async def post(self, widget: Widget) -> None:
        await self.query_one("#contents").mount(widget)

    @on(MarkdownTextArea.Submitted)
    async def on_user(self, event: MarkdownTextArea.Submitted) -> None:
        markdown = event.markdown.strip()
        event.stop()
        if markdown:
            if markdown == "/tree":
                self.new_content(DirectoryTree("./project"), throb=False)
            elif markdown.startswith("/edit"):
                path = markdown.partition(" ")[-1]
                await self.screen.query_one(Editor).open_file(
                    Path("./project") / Path(path)
                )
            elif markdown == "/shell":
                with self.app.suspend():
                    os.system("reset")
                    print("🐸  Press ctrl+D at any time to return to Toad!")
                    os.system("$SHELL")
            else:
                await self.post(Markdown(markdown, classes="user-input"))
                self.new_content(CodeOutput())

        else:
            self.app.bell()

    @work
    async def new_content(self, widget: Widget, throb: bool = True) -> None:
        if throb:
            throbber = ResponseWaiter()
            await self.post(throbber)
            self.app.show_throbber = True
            await asyncio.sleep(3)
            await throbber.remove()
            self.app.show_throbber = False
        await self.post(widget)


class Welcome(containers.VerticalGroup):
    def compose(self) -> ComposeResult:
        yield Static(ASCII_TOAD, classes="ascii-toad")
        yield Markdown(WELCOME_MD)


class ToadApp(App):
    CSS = """
    .ascii-toad {
        content-align: center middle;
        color: $success;
        padding: 1 2;        
    }
    .response {    
        margin-top: 1;
        margin-bottom: 1;    
        padding: 1 2;
        MarkdownBlock:last-of-type {
            margin-bottom: 0;
        }
    }
    
    Welcome {
        min-height: 100%;
        overflow: auto;
    }

    TextArea:blur {
        overflow: hidden;
    }

    Throbber {
        dock:top;
        # visibility: hidden;
    }

    """

    show_throbber = var(False)

    def compose(self) -> ComposeResult:
        yield Throbber().data_bind(show=ToadApp.show_throbber)
        with containers.Horizontal():
            yield Editor()
            yield Conversation()

    async def on_ready(self) -> None:
        self.theme = "dracula"
        conversation = self.query_one(Conversation)
        await conversation.post(Welcome())
        # await conversation.post(Static(ASCII_TOAD, classes="ascii-toad"))
        # await conversation.post(Markdown(WELCOME_MD, classes="welcome"))
        conversation.query_one("TextArea").focus()


if __name__ == "__main__":
    app = ToadApp()
    app.run()
