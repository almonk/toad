from textual.cache import LRUCache
from textual.content import Content
from textual import events
from textual.selection import Selection
from textual.style import Style
from textual.geometry import Size
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.timer import Timer

from toad import ansi


class Terminal(ScrollView):
    CURSOR_STYLE = Style.parse("reverse")

    def __init__(
        self,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
        minimum_terminal_width: int = -1,
    ):
        super().__init__(
            name=name,
            id=id,
            classes=classes,
            disabled=disabled,
        )
        self.minimum_terminal_width = minimum_terminal_width
        self.state = ansi.TerminalState()
        self._update_timer: Timer | None = None
        self._width: int = 80

        self.max_line_width = 0
        self.max_window_width = 0

        self._terminal_render_cache: LRUCache[tuple, Strip] = LRUCache(1024)

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        """Get the text under the selection.

        Args:
            selection: Selection information.

        Returns:
            Tuple of extracted text and ending (typically "\n" or " "), or `None` if no text could be extracted.
        """
        text = "\n".join(
            line_record.content.plain for line_record in self.state.buffer.lines
        )
        return selection.extract(text), "\n"

    def _on_resize(self, event: events.Resize) -> None:
        self._terminal_render_cache.grow(event.size.height * 2)
        self._update_width()

    def _update_width(self) -> None:
        window_width = self.scrollable_content_region.width or 80
        if window_width == self._width:
            return
        # self._width = window_width
        self.max_window_width = max(self.max_window_width, window_width)
        if self.minimum_terminal_width == -1 and window_width:
            self.minimum_terminal_width = window_width
        width = max(
            self.minimum_terminal_width,
            max(min(self.max_line_width, self.max_window_width), window_width),
        )
        self._width = width
        self.state.update_size(width=self._width)
        self._terminal_render_cache.clear()
        self.refresh()

    def on_mount(self) -> None:
        self.auto_links = False
        self.anchor()
        self.call_after_refresh(self._update_width)

    def write(self, text: str) -> None:
        self.state.write(text)
        self._update_from_state()
        # if self._update_timer is None:
        #     self._update_timer = self.set_timer(1 / 60, self._update_from_state)

    def _update_from_state(self) -> None:
        width = self.state.width
        height = self.state.buffer.line_count
        self.virtual_size = Size(min(self.state.buffer.max_line_width, width), height)
        if self._anchored and not self._anchor_released:
            self.scroll_y = self.max_scroll_y
        self._update_timer = None
        self.refresh()

    def render_line(self, y: int) -> Strip:
        scroll_x, scroll_y = self.scroll_offset
        strip = self._render_line(scroll_x, scroll_y + y, self._width)
        return strip

    def _render_line(self, x: int, y: int, width: int) -> Strip:
        selection = self.text_selection
        visual_style = self.visual_style
        rich_style = visual_style.rich_style

        state = self.state
        buffer = state.buffer

        buffer = state.scrollback_buffer
        buffer_offset = 0
        if y > len(buffer.folded_lines):
            buffer_offset = len(buffer.folded_lines)
            buffer = state.alternate_buffer

        try:
            line_no, line_offset, offset, line, updates = buffer.folded_lines[
                y - buffer_offset
            ]
        except IndexError:
            return Strip.blank(width, rich_style)

        cache_key: tuple | None = (self.state.alternate_screen, y, updates)
        if state.show_cursor and buffer.cursor_line == y - buffer_offset:
            if buffer.cursor_offset >= len(line):
                line = line.pad_right(buffer.cursor_offset - len(line) + 1)
            line_cursor_offset = buffer.cursor_offset

            line = line.stylize(
                self.CURSOR_STYLE, line_cursor_offset, line_cursor_offset + 1
            )
            cache_key = None

        if (
            not selection
            and cache_key is not None
            and (cached_strip := self._terminal_render_cache.get(cache_key))
        ):
            cached_strip = cached_strip.crop_extend(x, x + width, rich_style)
            cached_strip = cached_strip.apply_offsets(x + offset, line_no)
            return cached_strip

        if selection is not None:
            if select_span := selection.get_span(line_no):
                unfolded_content = buffer.lines[line_no].content.expand_tabs(8)
                start, end = select_span
                if end == -1:
                    end = len(unfolded_content)
                selection_style = self.screen.get_visual_style("screen--selection")
                unfolded_content = unfolded_content.stylize(selection_style, start, end)
                try:
                    line = (
                        self.state._fold_line(line_no, unfolded_content, width)[
                            line_offset
                        ]
                    ).content
                    cache_key = None
                except IndexError:
                    pass

        # if line.cell_length < width:
        #     line = line.extend_right(width - line.cell_length)
        strip = Strip(line.render_segments(visual_style), cell_length=line.cell_length)

        if cache_key is not None:
            self._terminal_render_cache[cache_key] = strip

        strip = strip.crop_extend(x, x + width, rich_style)
        strip = strip.apply_offsets(x + offset, line_no)

        return strip


if __name__ == "__main__":
    from textual.app import App, ComposeResult

    TEST = (
        "\033[31mThis is red text\033[0m\n"
        "\033[32mThis is green text\033[0m\n"
        "\033[33mThis is yellow text\033[0m\n"
        "\033[34mThis is blue text\033[0m\n"
        "\033[35mThis is magenta text\033[0m\n"
        "\033[36mThis is cyan text\033[0m\n"
        "\033[1mThis is bold text\033[0m\n"
        "\033[4mThis is underlined text\033[0m\n"
        "\033[1;31mThis is bold red text\033[0m\n"
        "\033[42mThis has a green background\033[0m\n"
        "\033[97;44mWhite text on blue background\033[0m"
    )

    class TApp(App):
        def compose(self) -> ComposeResult:
            yield Terminal()

        def on_mount(self) -> None:
            terminal = self.query_one(Terminal)
            terminal.write(TEST)

    app = TApp()
    app.run()
