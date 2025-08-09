from __future__ import annotations

from functools import cached_property
import os
from typing import TYPE_CHECKING
import asyncio
from contextlib import suppress
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual import containers
from textual import getters
from textual import events
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Static
from textual.widgets._markdown import MarkdownBlock, MarkdownFence
from textual.geometry import Offset, Spacing
from textual.reactive import var
from textual.css.query import NoMatches
from textual.layouts.grid import GridLayout


import llm

from toad import messages
from toad.widgets.menu import Menu
from toad.widgets.prompt import MarkdownTextArea, Prompt
from toad.widgets.throbber import Throbber
from toad.widgets.user_input import UserInput
from toad.widgets.explain import Explain
from toad.widgets.run_output import RunOutput

from toad.menus import CONVERSATION_MENUS

if TYPE_CHECKING:
    from toad.app import ToadApp

MD = """\
# Textual Markdown Browser - Demo

This Markdown file contains some examples of Markdown widgets.

## Headers

Headers levels 1 through 6 are supported.

### This is H3

This is H3 Content

#### This is H4

Header level 4 content. Drilling down into finer headings.

##### This is H5

Header level 5 content.

###### This is H6

Header level 6 content.

## Typography

The usual Markdown typography is supported. The exact output depends on your terminal, although most are fairly consistent.

### Emphasis

Emphasis is rendered with `*asterisks*`, and looks *like this*;

### Strong

Use two asterisks to indicate strong which renders in bold, e.g. `**strong**` render **strong**.

### Strikethrough

Two tildes indicates strikethrough, e.g. `~~cross out~~` render ~~cross out~~.

### Inline code ###

Inline code is indicated by backticks. e.g. `import this`.

## Horizontal rule

Draw a horizontal rule with three dashes (`---`).

---

Good for natural breaks in the content, that don't require another header.

[like this][example]

## Lists

1. Lists can be ordered
2. Lists can be unordered
   - I must not fear.
     - Fear is the mind-killer.
       - Fear is the little-death that brings total obliteration.
         - I will face my fear.
           - I will permit it to pass over me and through me.
     - And when it has gone past, I will turn the inner eye to see its path.
   - Where the fear has gone there will be nothing. Only I will remain.

[example]: example.com
   
### Longer list

1. **Duke Leto I Atreides**, head of House Atreides
2. **Lady Jessica**, Bene Gesserit and concubine of Leto, and mother of Paul and Alia
3. **Paul Atreides**, son of Leto and Jessica
4. **Alia Atreides**, daughter of Leto and Jessica
5. **Gurney Halleck**, troubadour warrior of House Atreides
6. **Thufir Hawat**, Mentat and Master of Assassins of House Atreides
7. **Duncan Idaho**, swordmaster of House Atreides
8. **Dr. Wellington Yueh**, Suk doctor of House Atreides
9. **Leto**, first son of Paul and Chani who dies as a toddler
10. **Esmar Tuek**, a smuggler on Arrakis
11. **Staban Tuek**, son of Esmar

## Fences

Fenced code blocks are introduced with three back-ticks and the optional parser. Here we are rendering the code in a sub-widget with syntax highlighting and indent guides.

In the future I think we could add controls to export the code, copy to the clipboard. Heck, even run it and show the output?

```python
@lru_cache(maxsize=1024)
def split(self, cut_x: int, cut_y: int) -> tuple[Region, Region, Region, Region]:
    \"\"\"Split a region into 4 from given x and y offsets (cuts).

    ```
                cut_x ↓
            ┌────────┐ ┌───┐
            │        │ │   │
            │    0   │ │ 1 │
            │        │ │   │
    cut_y → └────────┘ └───┘
            ┌────────┐ ┌───┐
            │    2   │ │ 3 │
            └────────┘ └───┘
    ```

    Args:
        cut_x (int): Offset from self.x where the cut should be made. If negative, the cut
            is taken from the right edge.
        cut_y (int): Offset from self.y where the cut should be made. If negative, the cut
            is taken from the lower edge.

    Returns:
        tuple[Region, Region, Region, Region]: Four new regions which add up to the original (self).
    \"\"\"

    x, y, width, height = self
    if cut_x < 0:
        cut_x = width + cut_x
    if cut_y < 0:
        cut_y = height + cut_y

    _Region = Region
    return (
        _Region(x, y, cut_x, cut_y),
        _Region(x + cut_x, y, width - cut_x, cut_y),
        _Region(x, y + cut_y, cut_x, height - cut_y),
        _Region(x + cut_x, y + cut_y, width - cut_x, height - cut_y),
    )
```

## Quote

Quotes are introduced with a chevron, and render like this:

> I must not fear.
> Fear is the mind-killer.
> Fear is the little-death that brings total obliteration.
> I will face my fear.
> I will permit it to pass over me and through me.
> And when it has gone past, I will turn the inner eye to see its path.
> Where the fear has gone there will be nothing. Only I will remain."

Quotes nest nicely. Here's what quotes within quotes look like:

> I must not fear.
> > Fear is the mind-killer.
> > Fear is the little-death that brings total obliteration.
> > I will face my fear.
> > > I will permit it to pass over me and through me.
> > > And when it has gone past, I will turn the inner eye to see its path.
> > > Where the fear has gone there will be nothing. Only I will remain.

## Tables

Tables are supported, and render as a Rich table.

I would like to add controls to these widgets to export the table as CSV, which I think would be a nice feature. In the future we might also have sortable columns by clicking on the headers.


| Name            | Type   | Default | Description                        |
| --------------- | ------ | ------- | ---------------------------------- |
| `show_header`   | `bool` | `True`  | Show the **table** header              |
| `fixed_rows`    | `int`  | `0`     | Number of fixed rows               |
| `fixed_columns` | `int`  | `0`     | Number of fixed columns            |
| `zebra_stripes` | `bool` | `False` | Display alternating colors on rows |
| `header_height` | `int`  | `1`     | Height of header row               |
| `show_cursor`   | `bool` | `True`  | Show a cell cursor                 |
"""

# MD = """
# ## Tables

# Tables are supported, and render as a Rich table.

# I would like to add controls to these widgets to export the table as CSV, which I think would be a nice feature. In the future we might also have sortable columns by clicking on the headers.

# `FOO`

# | Name            | Type   | Default | Description                        |
# | --------------- | ------ | ------- | ---------------------------------- |
# | `show_header`   | `bool` | `True`  | Show the **table** header              |
# | `fixed_rows`    | `int`  | `0`     | Number of fixed rows               |
# | `fixed_columns` | `int`  | `0`     | Number of fixed columns            |
# | `zebra_stripes` | `bool` | `False` | Display alternating colors on rows |
# | `header_height` | `int`  | `1`     | Height of header row               |
# | `show_cursor`   | `bool` | `True`  | Show a cell cursor                 |
# """

# MD = """
# ```python
# for n in range(10):
#     print(n)
# """

# MD = """
# 1. Lists can be ordered
# 2. Lists can be `unordered`
#    - I must not *fear*.
#      - Fear is the `mind-killer`.
#        - Fear is the little-death that brings total obliteration.
#          - I will face my fear.
#            - I will permit it to pass over me and through me.
#      - And when it has gone past, I will turn the inner eye to see its path.
#    - Where the fear has gone there will be nothing. Only I will remain.
# """

MD = """
```python
def mandelbrot(c: complex, max_iter: int) -> int:
    \"\"\"Determine the number of iterations for a point in the Mandelbrot set.

    Args:
        c (complex): The complex point to test.
        max_iter (int): The maximum number of iterations to test.

    Returns:
        int: Number of iterations before escape or max_iter.
    \"\"\"
    z = 0 + 0j
    for n in range(max_iter):
        if abs(z) > 2:
            return n
        z = z * z + c
    return max_iter

def colorize(iter_count: int, max_iter: int) -> str:
    \"\"\"Get an ANSI color code based on the iteration count.

    Args:
        iter_count (int): Number of iterations completed before escape.
        max_iter (int): Maximum number of iterations allowed.

    Returns:
        str: ANSI escape code for color.
    \"\"\"
    if iter_count == max_iter:
        return "\\033[48;5;0m"  # Black background for points in the set
    else:
        # Create a gradient from 17 to 231 (blue to red) for escaping points
        color_code = 17 + int((iter_count / max_iter) * 214)
        return f"\\033[48;5;{color_code}m"

def draw_mandelbrot(width: int, height: int, max_iter: int) -> None:
    \"\"\"Draw the Mandelbrot set in the terminal using ANSI colors.

    Args:
        width (int): Width of the output in terminal characters.
        height (int): Height of the output in terminal rows.
        max_iter (int): Maximum number of iterations for Mandelbrot calculation.
    \"\"\"
    for y in range(height):
        for x in range(width):
            # Map the (x, y) pixel to a point in the complex plane
            real = (x / width) * 3.5 - 2.5
            imag = (y / height) * 2.0 - 1.0
            c = complex(real, imag)
            
            # Calculate the number of iterations
            iter_count = mandelbrot(c, max_iter)
            
            # Get the color for this point and print a space (box)
            color = colorize(iter_count, max_iter)
            print(f"{color}  ", end="")

        # Reset color and move to the next line
        print("\\033[0m")

# Configuration for drawing
width = 80    # Number of characters wide
height = 40   # Number of character rows
max_iter = 100  # Maximum iterations for Mandelbrot calculation

# Draw the Mandelbrot set
draw_mandelbrot(width, height, max_iter)
```
"""


class Cursor(Static):
    follow_widget: var[Widget | None] = var(None)
    blink = var(True, toggle_class="-blink")

    def on_mount(self) -> None:
        self.display = False
        self.blink_timer = self.set_interval(0.5, self._update_blink, pause=True)
        self.set_interval(0.4, self._update_follow)

    def _update_blink(self) -> None:
        self.blink = not self.blink

    def watch_follow_widget(self, widget: Widget | None) -> None:
        self.display = widget is not None

    def _update_follow(self) -> None:
        if self.follow_widget:
            self.styles.height = max(1, self.follow_widget.size.height)
            follow_y = (
                self.follow_widget.virtual_region.y
                + self.follow_widget.parent.virtual_region.y
            )
            self.offset = Offset(0, follow_y)

    def follow(self, widget: Widget | None) -> None:
        self.follow_widget = widget
        self.blink = False
        if widget is None:
            self.display = False
            self.blink_timer.reset()
            self.blink_timer.pause()
        else:
            self.display = True
            self.blink_timer.reset()
            self.blink_timer.resume()
            self._update_follow()


class Contents(containers.VerticalGroup, can_focus=False):
    pass


class ContentsGrid(containers.Grid):
    def pre_layout(self, layout) -> None:
        assert isinstance(layout, GridLayout)
        layout.stretch_height = True


class Window(containers.VerticalScroll):
    BINDING_GROUP_TITLE = "View"
    BINDINGS = [Binding("end", "screen.focus_prompt", "Focus prompt")]


class Conversation(containers.Vertical):
    BINDING_GROUP_TITLE = "Conversation"
    BINDINGS = [
        Binding("alt+up", "cursor_up", "Block up", priority=True),
        Binding("alt+down", "cursor_down", "Block down"),
        Binding("enter", "select_block", "Select"),
        Binding("escape", "dismiss", "Dismiss", show=False),
        Binding("f2,ctrl+comma", "settings", "Settings"),
    ]

    busy_count = var(0)
    block_cursor = var(-1)
    _blocks: var[list[MarkdownBlock] | None] = var(None)

    throbber: getters.query_one[Throbber] = getters.query_one("#throbber")
    contents = getters.query_one(Contents)
    window = getters.query_one(Window)
    cursor = getters.query_one(Cursor)
    prompt = getters.query_one(Prompt)

    app: ToadApp

    def compose(self) -> ComposeResult:
        yield Throbber(id="throbber")
        with Window():
            with ContentsGrid():
                with containers.VerticalGroup(id="cursor-container"):
                    yield Cursor()
                yield Contents(id="contents")
        yield Prompt()

    @cached_property
    def conversation(self) -> llm.Conversation:
        return llm.get_model(self.app.settings.get("llm.model", str)).conversation()

    @property
    def cursor_block(self) -> MarkdownBlock | None:
        """The block next to the cursor, or `None` if no block cursor."""
        blocks = self.blocks
        if self.block_cursor < 0 or self.block_cursor >= len(blocks):
            return None
        return blocks[self.block_cursor]

    @on(messages.WorkStarted)
    def on_work_started(self) -> None:
        self.busy_count += 1

    @on(messages.WorkFinished)
    def on_work_finished(self) -> None:
        self.busy_count -= 1

    @on(messages.UserInputSubmitted)
    async def on_user_input_submitted(self, event: messages.UserInputSubmitted) -> None:
        from toad.widgets.agent_response import AgentResponse

        await self.post(UserInput(event.body))
        agent_response = AgentResponse(self.conversation)
        await self.post(agent_response)
        agent_response.send_prompt(event.body)

    @on(Menu.OptionSelected)
    async def on_menu_option_selected(self, event: Menu.OptionSelected) -> None:
        await self.run_action(event.action)

    @on(events.DescendantFocus)
    def on_descendant_focus(self, event: events.DescendantFocus):
        if isinstance(event.widget, MarkdownTextArea):
            self.block_cursor = -1

    @on(events.DescendantBlur)
    def on_descendant_blur(self, event: events.DescendantBlur):
        if isinstance(event.widget, Window):
            self.cursor.visible = False

    @on(Menu.Dismissed)
    def on_menu_dismissed(self, event: Menu.Dismissed) -> None:
        event.stop()
        self.cursor.visible = True
        with self.window.prevent(events.DescendantFocus):
            self.window.focus(scroll_visible=False)
        event.menu.remove()

    def watch_busy_count(self, busy: int) -> None:
        self.throbber.set_class(busy > 0, "-busy")

    async def on_mount(self) -> None:
        self.call_after_refresh(self.post_welcome)
        self.app.settings_changed_signal.subscribe(self, self._settings_changed)

    def _settings_changed(self, setting_item: tuple[str, str]) -> None:
        key, value = setting_item
        if key == "llm.model":
            self.conversation = llm.get_model(value).conversation()

    async def post_welcome(self) -> None:
        from toad.widgets.welcome import Welcome

        await self.post(Welcome(classes="note"), anchor=False)
        await self.post(
            Static(
                f"Settings read from [$text-success]'{self.app.settings_path}'",
                classes="note",
            )
        )
        notes_path = Path(__file__).parent / "../../../notes.md"
        from textual.widgets import Markdown

        await self.post(Markdown(notes_path.read_text(), classes="note"))

        # from toad.widgets.agent_response import AgentResponse

        # agent_response = AgentResponse(self.conversation)
        # await self.post(agent_response)
        # agent_response.update(MD)

    def on_click(self, event: events.Click) -> None:
        if event.widget is not None:
            markdown_block = event.widget
            try:
                if not isinstance(
                    markdown_block, MarkdownBlock
                ) or not markdown_block.has_class("level-0"):
                    markdown_block = event.widget.query_ancestor(
                        "MarkdownBlock.level-0", MarkdownBlock
                    )

            except NoMatches:
                pass
            else:
                with suppress(ValueError):
                    clicked_block_index = self.blocks.index(markdown_block)
                    if self.block_cursor == clicked_block_index:
                        pass
                        # await self.action_select_block()
                    else:
                        self.block_cursor = clicked_block_index

        # self.notify(str(event.widget))

    async def post(self, widget: Widget, anchor: bool = True) -> None:
        self._blocks = None
        await self.contents.mount(widget)
        if anchor:
            self.window.anchor()

    @property
    def blocks(self) -> list[MarkdownBlock]:
        from toad.widgets.agent_response import AgentResponse

        if self._blocks is None or self.busy_count:
            self._blocks = [
                block
                for response in self.contents.query_children(AgentResponse)
                for block in response.query_children(MarkdownBlock)
            ]
        return self._blocks

    def action_cursor_up(self) -> None:
        blocks = self.blocks
        if blocks:
            if self.block_cursor == 0:
                pass
            elif self.block_cursor == -1:
                self.block_cursor = len(blocks) - 1
            else:
                self.block_cursor -= 1

    def action_cursor_down(self) -> None:
        blocks = self.blocks
        if not blocks:
            return
        if self.block_cursor == -1:
            return
        else:
            if self.block_cursor < len(blocks) - 1:
                self.block_cursor += 1
            else:
                self.block_cursor = -1

    def action_dismiss(self) -> None:
        self.block_cursor = -1

    def focus_prompt(self) -> None:
        self.block_cursor = -1
        self.prompt.focus()

    async def action_select_block(self) -> None:
        block = self.blocks[self.block_cursor]
        if block.name is None:
            self.app.bell()
            return
        menu_options = CONVERSATION_MENUS.get(block.name, []).copy()

        from toad.code_analyze import get_special_name_from_code

        if block.name == "fence" and isinstance(block, MarkdownFence) and block.source:
            for numeral, name in enumerate(
                get_special_name_from_code(block.source, block.lexer), 1
            ):
                menu_options.append(
                    Menu.Item(f"explain('{name}')", f"Explain '{name}'", f"{numeral}")
                )

        menu = Menu(
            [
                Menu.Item("explain", "Explain this", "e"),
                Menu.Item("copy_to_clipboard", "Copy to clipboard", "c"),
                Menu.Item("copy_to_prompt", "Copy to prompt", "p"),
                *menu_options,
            ]
        )
        menu.offset = Offset(1, block.region.offset.y)
        await self.mount(menu)
        menu.focus()

    def action_copy_to_clipboard(self) -> None:
        if (block := self.cursor_block) is not None and block.source:
            self.app.copy_to_clipboard(block.source)
            self.notify("Copied to clipboard")

    def action_copy_to_prompt(self) -> None:
        if (block := self.cursor_block) is not None and block.source:
            self.block_cursor = -1
            self.prompt.append(block.source)

    def action_explain(self, topic: str | None = None) -> None:
        if (block := self.cursor_block) is not None and block.source:
            if topic:
                PROMPT = f"Explain the purpose of '{topic}' in the following code:\n{block.source}"
            else:
                PROMPT = f"Explain the following:\n{block.source}"
            self.screen.query_one(Explain).send_prompt(PROMPT)

    def action_run(self) -> None:
        if (block := self.cursor_block) is not None and block.source:
            assert isinstance(block, MarkdownFence)
            self.execute(block._content.plain, block.lexer)

    @work
    async def action_settings(self) -> None:
        from toad.screens.settings import SettingsScreen

        await self.app.push_screen_wait(SettingsScreen())
        self.app.save_settings()

    @work
    async def execute(self, code: str, language: str) -> None:
        self.notify(repr(language))
        if language == "python":
            command = "python run"
        elif language == "bash":
            command = "sh run"
        else:
            self.notify(
                f"Toad doesn't know how to run '{language}' code yet",
                title="Run",
                severity="error",
            )
        run_output = RunOutput()
        await self.post(run_output, anchor=True)
        with open("run", mode="wt", encoding="utf-8") as source:
            source.write(code)

        env = os.environ.copy()
        env["COLUMNS"] = str(self.size.width - 4)
        env["LINES"] = "24"
        env["TTY_COMPATIBLE"] = "1"

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        while data := await process.stdout.readline():
            line = data.decode("utf-8")
            run_output.write(line)
            # run_output.output += line

    def watch_block_cursor(self, block_cursor: int) -> None:
        if block_cursor == -1:
            self.cursor.follow(None)
            self.window.anchor()
            self.prompt.focus()
        else:
            self.window.focus()
            self.cursor.visible = True
            blocks = self.blocks
            block = blocks[block_cursor]
            self.cursor.follow(block)
            self.window.scroll_to_center(block)
