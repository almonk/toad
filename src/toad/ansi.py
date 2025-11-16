from __future__ import annotations

import rich.repr

import re
from dataclasses import dataclass, field
from functools import lru_cache
import io

from typing import Iterable, Literal, Mapping, NamedTuple, Sequence
from textual.color import Color
from textual.style import Style, NULL_STYLE
from textual.content import Content

from toad._stream_parser import (
    MatchToken,
    StreamParser,
    SeparatorToken,
    PatternToken,
    Pattern,
    PatternCheck,
    ParseResult,
)

from toad.dec import CHARSET_MAP


def as_int(text: str) -> int:
    """Convert a string to an integer, or return `0` if conversion is impossible"""
    if not text.isdecimal():
        return 0
    try:
        return int(text)
    except ValueError:
        return 0


class ANSIToken:
    pass


@dataclass
class ANSIContent(ANSIToken):
    text: str


@dataclass
class Separator(ANSIToken):
    text: str


@dataclass
class CSI(ANSIToken):
    text: str


@dataclass
class OSC(ANSIToken):
    text: str


@dataclass
class DEC(ANSIToken):
    slot: int
    character_set: str


@dataclass
class DECInvoke(ANSIToken):
    gl: int | None = None
    gr: int | None = None
    shift: int | None = None


class CSIPattern(Pattern):
    """Control Sequence Introducer."""

    PARAMETER_BYTES = frozenset([chr(codepoint) for codepoint in range(0x30, 0x3F + 1)])
    INTERMEDIATE_BYTES = frozenset(
        [chr(codepoint) for codepoint in range(0x20, 0x2F + 1)]
    )
    FINAL_BYTE = frozenset([chr(codepoint) for codepoint in range(0x40, 0x7E + 1)])

    class Match(NamedTuple):
        parameter: str
        intermediate: str
        final: str

        @property
        def full(self) -> str:
            return f"\x1b[{self.parameter}{self.intermediate}{self.final}"

    def check(self) -> PatternCheck:
        """Check a CSI pattern."""
        if (yield) != "[":
            return False

        parameter = io.StringIO()
        intermediate = io.StringIO()
        parameter_bytes = self.PARAMETER_BYTES

        while (character := (yield)) in parameter_bytes:
            parameter.write(character)

        if character in self.FINAL_BYTE:
            return self.Match(parameter.getvalue(), "", character)

        intermediate_bytes = self.INTERMEDIATE_BYTES
        while True:
            intermediate.write(character)
            if (character := (yield)) not in intermediate_bytes:
                break

        final_byte = character
        if final_byte not in self.FINAL_BYTE:
            return False

        return self.Match(
            parameter.getvalue(),
            intermediate.getvalue(),
            final_byte,
        )


class DECPattern(Pattern):
    def check(self) -> PatternCheck:
        if (initial_character := (yield)) not in "()*+":
            return False
        slot = "()*+".find(initial_character)
        character_set = yield
        return DEC(slot, character_set)


class DECInvokePattern(Pattern):
    INVOKE_G2_INTO_GL = DECInvoke(gl=2)
    INVOKE_G3_INTO_GL = DECInvoke(gl=3)
    INVOKE_G1_INTO_GR = DECInvoke(gr=1)
    INVOKE_G2_INTO_GR = DECInvoke(gr=2)
    INVOKE_G3_INTO_GR = DECInvoke(gr=3)
    SHIFT_G2 = DECInvoke(shift=2)
    SHIFT_G3 = DECInvoke(shift=3)

    INVOKE = {
        "n": INVOKE_G2_INTO_GL,
        "o": INVOKE_G3_INTO_GL,
        "~": INVOKE_G1_INTO_GR,
        "}": INVOKE_G2_INTO_GR,
        "|": INVOKE_G3_INTO_GR,
        "N": SHIFT_G2,
        "O": SHIFT_G3,
    }

    def check(self) -> PatternCheck:
        if (initial_character := (yield)) not in self.INVOKE:
            return False
        return self.INVOKE[initial_character]


class OSCPattern(Pattern):
    class Match(NamedTuple):
        code: str

    def check(self) -> PatternCheck:
        if (yield) != "]":
            return False
        return self.Match("]")


SGR_STYLE_MAP: Mapping[int, Style] = {
    1: Style(bold=True),
    2: Style(dim=True),
    3: Style(italic=True),
    4: Style(underline=True),
    5: Style(blink=True),
    6: Style(blink=True),
    7: Style(reverse=True),
    8: Style(reverse=True),
    9: Style(strike=True),
    21: Style(underline2=True),
    22: Style(dim=False, bold=False),
    23: Style(italic=False),
    24: Style(underline=False),
    25: Style(blink=False),
    26: Style(blink=False),
    27: Style(reverse=False),
    28: NULL_STYLE,  # "not conceal",
    29: Style(strike=False),
    30: Style(foreground=Color(0, 0, 0, ansi=0)),
    31: Style(foreground=Color(128, 0, 0, ansi=1)),
    32: Style(foreground=Color(0, 128, 0, ansi=2)),
    33: Style(foreground=Color(128, 128, 0, ansi=3)),
    34: Style(foreground=Color(0, 0, 128, ansi=4)),
    35: Style(foreground=Color(128, 0, 128, ansi=5)),
    36: Style(foreground=Color(0, 128, 128, ansi=6)),
    37: Style(foreground=Color(192, 192, 192, ansi=7)),
    39: Style(foreground=Color(0, 0, 0, ansi=-1)),
    40: Style(background=Color(0, 0, 0, ansi=0)),
    41: Style(background=Color(128, 0, 0, ansi=1)),
    42: Style(background=Color(0, 128, 0, ansi=2)),
    43: Style(background=Color(128, 128, 0, ansi=3)),
    44: Style(background=Color(0, 0, 128, ansi=4)),
    45: Style(background=Color(128, 0, 128, ansi=5)),
    46: Style(background=Color(0, 128, 128, ansi=6)),
    47: Style(background=Color(192, 192, 192, ansi=7)),
    49: Style(background=Color(0, 0, 0, ansi=-1)),
    51: NULL_STYLE,  # "frame",
    52: NULL_STYLE,  # "encircle",
    53: NULL_STYLE,  # "overline",
    54: NULL_STYLE,  # "not frame not encircle",
    55: NULL_STYLE,  # "not overline",
    90: Style(foreground=Color(128, 128, 128, ansi=8)),
    91: Style(foreground=Color(255, 0, 0, ansi=9)),
    92: Style(foreground=Color(0, 255, 0, ansi=10)),
    93: Style(foreground=Color(255, 255, 0, ansi=11)),
    94: Style(foreground=Color(0, 0, 255, ansi=12)),
    95: Style(foreground=Color(255, 0, 255, ansi=13)),
    96: Style(foreground=Color(0, 255, 255, ansi=14)),
    97: Style(foreground=Color(255, 255, 255, ansi=15)),
    100: Style(background=Color(128, 128, 128, ansi=8)),
    101: Style(background=Color(255, 0, 0, ansi=9)),
    102: Style(background=Color(0, 255, 0, ansi=10)),
    103: Style(background=Color(255, 255, 0, ansi=11)),
    104: Style(background=Color(0, 0, 255, ansi=12)),
    105: Style(background=Color(255, 0, 255, ansi=13)),
    106: Style(background=Color(0, 255, 255, ansi=14)),
    107: Style(background=Color(255, 255, 255, ansi=15)),
}


class ANSIParser(StreamParser[ANSIToken]):
    """Parse a stream of text containing escape sequences in to logical tokens."""

    def parse(self) -> ParseResult[ANSIToken]:
        NEW_LINE = "\n"
        CARRIAGE_RETURN = "\r"
        ESCAPE = "\x1b"
        BACKSPACE = "\x08"

        while True:
            token = yield self.read_until(NEW_LINE, CARRIAGE_RETURN, ESCAPE, BACKSPACE)

            if isinstance(token, SeparatorToken):
                if token.text == ESCAPE:
                    token = yield self.read_patterns(
                        "\x1b",
                        csi=CSIPattern(),
                        osc=OSCPattern(),
                        dec=DECPattern(),
                        dec_invoke=DECInvokePattern(),
                    )

                    if isinstance(token, PatternToken):
                        value = token.value

                        if isinstance(value, CSIPattern.Match):
                            yield CSI(value.full)

                        elif isinstance(value, OSCPattern.Match):
                            osc_data: list[str] = []

                            while not isinstance(
                                token := (yield self.read_regex(r"\x1b\\|\x07")),
                                MatchToken,
                            ):
                                osc_data.append(token.text)
                            yield OSC("".join(osc_data))

                        elif isinstance(value, DEC):
                            yield value

                        elif isinstance(value, DECInvoke):
                            yield value

                else:
                    yield Separator(token.text)
                continue

            yield ANSIContent(token.text)


EMPTY_LINE = Content()


ANSI_COLORS: Sequence[str] = [
    "ansi_black",
    "ansi_red",
    "ansi_green",
    "ansi_yellow",
    "ansi_blue",
    "ansi_magenta",
    "ansi_cyan",
    "ansi_white",
    "ansi_bright_black",
    "ansi_bright_red",
    "ansi_bright_green",
    "ansi_bright_yellow",
    "ansi_bright_blue",
    "ansi_bright_magenta",
    "ansi_bright_cyan",
    "ansi_bright_white",
    "rgb(0,0,0)",
    "rgb(0,0,95)",
    "rgb(0,0,135)",
    "rgb(0,0,175)",
    "rgb(0,0,215)",
    "rgb(0,0,255)",
    "rgb(0,95,0)",
    "rgb(0,95,95)",
    "rgb(0,95,135)",
    "rgb(0,95,175)",
    "rgb(0,95,215)",
    "rgb(0,95,255)",
    "rgb(0,135,0)",
    "rgb(0,135,95)",
    "rgb(0,135,135)",
    "rgb(0,135,175)",
    "rgb(0,135,215)",
    "rgb(0,135,255)",
    "rgb(0,175,0)",
    "rgb(0,175,95)",
    "rgb(0,175,135)",
    "rgb(0,175,175)",
    "rgb(0,175,215)",
    "rgb(0,175,255)",
    "rgb(0,215,0)",
    "rgb(0,215,95)",
    "rgb(0,215,135)",
    "rgb(0,215,175)",
    "rgb(0,215,215)",
    "rgb(0,215,255)",
    "rgb(0,255,0)",
    "rgb(0,255,95)",
    "rgb(0,255,135)",
    "rgb(0,255,175)",
    "rgb(0,255,215)",
    "rgb(0,255,255)",
    "rgb(95,0,0)",
    "rgb(95,0,95)",
    "rgb(95,0,135)",
    "rgb(95,0,175)",
    "rgb(95,0,215)",
    "rgb(95,0,255)",
    "rgb(95,95,0)",
    "rgb(95,95,95)",
    "rgb(95,95,135)",
    "rgb(95,95,175)",
    "rgb(95,95,215)",
    "rgb(95,95,255)",
    "rgb(95,135,0)",
    "rgb(95,135,95)",
    "rgb(95,135,135)",
    "rgb(95,135,175)",
    "rgb(95,135,215)",
    "rgb(95,135,255)",
    "rgb(95,175,0)",
    "rgb(95,175,95)",
    "rgb(95,175,135)",
    "rgb(95,175,175)",
    "rgb(95,175,215)",
    "rgb(95,175,255)",
    "rgb(95,215,0)",
    "rgb(95,215,95)",
    "rgb(95,215,135)",
    "rgb(95,215,175)",
    "rgb(95,215,215)",
    "rgb(95,215,255)",
    "rgb(95,255,0)",
    "rgb(95,255,95)",
    "rgb(95,255,135)",
    "rgb(95,255,175)",
    "rgb(95,255,215)",
    "rgb(95,255,255)",
    "rgb(135,0,0)",
    "rgb(135,0,95)",
    "rgb(135,0,135)",
    "rgb(135,0,175)",
    "rgb(135,0,215)",
    "rgb(135,0,255)",
    "rgb(135,95,0)",
    "rgb(135,95,95)",
    "rgb(135,95,135)",
    "rgb(135,95,175)",
    "rgb(135,95,215)",
    "rgb(135,95,255)",
    "rgb(135,135,0)",
    "rgb(135,135,95)",
    "rgb(135,135,135)",
    "rgb(135,135,175)",
    "rgb(135,135,215)",
    "rgb(135,135,255)",
    "rgb(135,175,0)",
    "rgb(135,175,95)",
    "rgb(135,175,135)",
    "rgb(135,175,175)",
    "rgb(135,175,215)",
    "rgb(135,175,255)",
    "rgb(135,215,0)",
    "rgb(135,215,95)",
    "rgb(135,215,135)",
    "rgb(135,215,175)",
    "rgb(135,215,215)",
    "rgb(135,215,255)",
    "rgb(135,255,0)",
    "rgb(135,255,95)",
    "rgb(135,255,135)",
    "rgb(135,255,175)",
    "rgb(135,255,215)",
    "rgb(135,255,255)",
    "rgb(175,0,0)",
    "rgb(175,0,95)",
    "rgb(175,0,135)",
    "rgb(175,0,175)",
    "rgb(175,0,215)",
    "rgb(175,0,255)",
    "rgb(175,95,0)",
    "rgb(175,95,95)",
    "rgb(175,95,135)",
    "rgb(175,95,175)",
    "rgb(175,95,215)",
    "rgb(175,95,255)",
    "rgb(175,135,0)",
    "rgb(175,135,95)",
    "rgb(175,135,135)",
    "rgb(175,135,175)",
    "rgb(175,135,215)",
    "rgb(175,135,255)",
    "rgb(175,175,0)",
    "rgb(175,175,95)",
    "rgb(175,175,135)",
    "rgb(175,175,175)",
    "rgb(175,175,215)",
    "rgb(175,175,255)",
    "rgb(175,215,0)",
    "rgb(175,215,95)",
    "rgb(175,215,135)",
    "rgb(175,215,175)",
    "rgb(175,215,215)",
    "rgb(175,215,255)",
    "rgb(175,255,0)",
    "rgb(175,255,95)",
    "rgb(175,255,135)",
    "rgb(175,255,175)",
    "rgb(175,255,215)",
    "rgb(175,255,255)",
    "rgb(215,0,0)",
    "rgb(215,0,95)",
    "rgb(215,0,135)",
    "rgb(215,0,175)",
    "rgb(215,0,215)",
    "rgb(215,0,255)",
    "rgb(215,95,0)",
    "rgb(215,95,95)",
    "rgb(215,95,135)",
    "rgb(215,95,175)",
    "rgb(215,95,215)",
    "rgb(215,95,255)",
    "rgb(215,135,0)",
    "rgb(215,135,95)",
    "rgb(215,135,135)",
    "rgb(215,135,175)",
    "rgb(215,135,215)",
    "rgb(215,135,255)",
    "rgb(215,175,0)",
    "rgb(215,175,95)",
    "rgb(215,175,135)",
    "rgb(215,175,175)",
    "rgb(215,175,215)",
    "rgb(215,175,255)",
    "rgb(215,215,0)",
    "rgb(215,215,95)",
    "rgb(215,215,135)",
    "rgb(215,215,175)",
    "rgb(215,215,215)",
    "rgb(215,215,255)",
    "rgb(215,255,0)",
    "rgb(215,255,95)",
    "rgb(215,255,135)",
    "rgb(215,255,175)",
    "rgb(215,255,215)",
    "rgb(215,255,255)",
    "rgb(255,0,0)",
    "rgb(255,0,95)",
    "rgb(255,0,135)",
    "rgb(255,0,175)",
    "rgb(255,0,215)",
    "rgb(255,0,255)",
    "rgb(255,95,0)",
    "rgb(255,95,95)",
    "rgb(255,95,135)",
    "rgb(255,95,175)",
    "rgb(255,95,215)",
    "rgb(255,95,255)",
    "rgb(255,135,0)",
    "rgb(255,135,95)",
    "rgb(255,135,135)",
    "rgb(255,135,175)",
    "rgb(255,135,215)",
    "rgb(255,135,255)",
    "rgb(255,175,0)",
    "rgb(255,175,95)",
    "rgb(255,175,135)",
    "rgb(255,175,175)",
    "rgb(255,175,215)",
    "rgb(255,175,255)",
    "rgb(255,215,0)",
    "rgb(255,215,95)",
    "rgb(255,215,135)",
    "rgb(255,215,175)",
    "rgb(255,215,215)",
    "rgb(255,215,255)",
    "rgb(255,255,0)",
    "rgb(255,255,95)",
    "rgb(255,255,135)",
    "rgb(255,255,175)",
    "rgb(255,255,215)",
    "rgb(255,255,255)",
    "rgb(8,8,8)",
    "rgb(18,18,18)",
    "rgb(28,28,28)",
    "rgb(38,38,38)",
    "rgb(48,48,48)",
    "rgb(58,58,58)",
    "rgb(68,68,68)",
    "rgb(78,78,78)",
    "rgb(88,88,88)",
    "rgb(98,98,98)",
    "rgb(108,108,108)",
    "rgb(118,118,118)",
    "rgb(128,128,128)",
    "rgb(138,138,138)",
    "rgb(148,148,148)",
    "rgb(158,158,158)",
    "rgb(168,168,168)",
    "rgb(178,178,178)",
    "rgb(188,188,188)",
    "rgb(198,198,198)",
    "rgb(208,208,208)",
    "rgb(218,218,218)",
    "rgb(228,228,228)",
    "rgb(238,238,238)",
]


type ClearType = Literal["cursor_to_end", "cursor_to_beginning", "screen", "scrollback"]
ANSI_CLEAR: Mapping[int, ClearType] = {
    0: "cursor_to_end",
    1: "cursor_to_beginning",
    2: "screen",
    3: "scrollback",
}


@rich.repr.auto
class ANSICursor(NamedTuple):
    """Represents a single operation on the ANSI output.

    All values may be `None` meaning "not set".
    """

    delta_x: int | None = None
    """Relative x change."""
    delta_y: int | None = None
    """Relative y change."""
    absolute_x: int | None = None
    """Replace x."""
    absolute_y: int | None = None
    """Replace y."""
    text: str | None = None
    """New text"""
    replace: tuple[int | None, int | None] | None = None
    """Replace range (slice like)."""

    def __rich_repr__(self) -> rich.repr.Result:
        yield "delta_x", self.delta_x, None
        yield "delta_y", self.delta_y, None
        yield "absolute_x", self.absolute_x, None
        yield "absolute_y", self.absolute_y, None
        yield "text", self.text, None
        yield "replace", self.replace, None

    def get_replace_offsets(
        self, cursor_offset: int, line_length: int
    ) -> tuple[int, int]:
        assert self.replace is not None, (
            "Only call this if the replace attribute has a value"
        )
        replace_start, replace_end = self.replace
        if replace_start is None:
            replace_start = cursor_offset
        if replace_end is None:
            replace_end = cursor_offset
        if replace_start < 0:
            replace_start = line_length + replace_start
        if replace_end < 0:
            replace_end = line_length + replace_end
        return (replace_start, replace_end)


@rich.repr.auto
class ANSIStyle(NamedTuple):
    """Update style."""

    style: Style


@rich.repr.auto
class ANSIClear(NamedTuple):
    """Enumare for clearing the 'screen'."""

    clear: ClearType


@rich.repr.auto
class ANSICursorShow(NamedTuple):
    """Toggle visibility of the cursor."""

    show: bool


@rich.repr.auto
class ANSIScrollMargin(NamedTuple):
    top: int | None = None
    bottom: int | None = None


@rich.repr.auto
class ANSIAlternateScreen(NamedTuple):
    """Toggle the alternate buffer."""

    enable: bool


# Not technically part of the terminal protocol
@rich.repr.auto
class ANSIWorkingDirectory(NamedTuple):
    """Working directory changed"""

    path: str


@rich.repr.auto
class ANSICharacterSet(NamedTuple):
    """Updated character set state."""

    dec: DEC | None = None
    dec_invoke: DECInvoke | None = None


type ANSICommand = (
    ANSIStyle
    | ANSICursor
    | ANSIClear
    | ANSICursorShow
    | ANSIScrollMargin
    | ANSIAlternateScreen
    | ANSIWorkingDirectory
    | ANSICharacterSet
)


class ANSIStream:
    def __init__(self) -> None:
        self.parser = ANSIParser()
        self.style = Style()
        self.show_cursor = True

    @classmethod
    @lru_cache(maxsize=1024)
    def _parse_sgr(cls, sgr: str) -> Style | None:
        """Parse a SGR (Select Graphics Rendition) code in to a Style instance,
        or `None` to indicate a reset.

        Args:
            sgr: SGR sequence.

        Returns:
            A Visual Style, or `None`.
        """
        codes = [
            code if code < 255 else 255
            for code in map(int, [sgr_code or "0" for sgr_code in sgr.split(";")])
        ]
        style = NULL_STYLE
        while codes:
            match codes:
                case [38, 2, red, green, blue, *codes]:
                    # Foreground RGB
                    style += Style(foreground=Color(red, green, blue))
                case [48, 2, red, green, blue, *codes]:
                    # Background RGB
                    style += Style(background=Color(red, green, blue))
                case [38, 5, ansi_color, *codes]:
                    # Foreground ANSI
                    style += Style(foreground=Color.parse(ANSI_COLORS[ansi_color]))
                case [48, 5, ansi_color, *codes]:
                    # Background ANSI
                    style += Style(background=Color.parse(ANSI_COLORS[ansi_color]))
                case [0, *codes]:
                    # reset
                    return None
                case [code, *codes]:
                    if sgr_style := SGR_STYLE_MAP.get(code):
                        style += sgr_style

        return style

    def feed(self, text: str) -> Iterable[ANSICommand]:
        """Feed text potentially containing ANSI sequences, and parse in to
        an iterable of ansi commands.

        Args:
            text: Text to feed.

        Yields:
            `ANSICommand` isntances.
        """
        print(repr(text))
        for token in self.parser.feed(text):
            # print("TOKEN", repr(token))
            if isinstance(token, ANSIToken):
                yield from self.on_token(token)

    ANSI_SEPARATORS = {
        "\n": ANSICursor(delta_y=+1, absolute_x=0),
        "\r": ANSICursor(absolute_x=0),
        "\x08": ANSICursor(delta_x=-1),
    }
    CLEAR_LINE_CURSOR_TO_END = ANSICursor(replace=(None, -1), text="")
    CLEAR_LINE_CURSOR_TO_BEGINNING = ANSICursor(replace=(0, None), text="")
    CLEAR_LINE = ANSICursor(replace=(0, -1), text="", absolute_x=0)
    CLEAR_SCREEN_CURSOR_TO_END = ANSIClear("cursor_to_end")
    CLEAR_SCREEN_CURSOR_TO_BEGINNING = ANSIClear("cursor_to_beginning")
    CLEAR_SCREEN = ANSIClear("screen")
    CLEAR_SCREEN_SCROLLBACK = ANSIClear("scrollback")
    SHOW_CURSOR = ANSICursorShow(True)
    HIDE_CURSOR = ANSICursorShow(False)
    ENABLE_ALTERNATE_SCREEN = ANSIAlternateScreen(True)
    DISABLE_ALTERNATE_SCREEN = ANSIAlternateScreen(False)

    @classmethod
    @lru_cache(maxsize=1024)
    def _parse_csi(cls, csi: str) -> ANSICommand | None:
        """Parse CSI sequence in to an ansi segment.

        Args:
            csi: CSI sequence.

        Returns:
            Ansi segment, or `None` if one couldn't be decoded.
        """

        if match := re.fullmatch(r"\x1b\[(\d+)?(?:;)?(\d*)?(\w)", csi):
            match match.groups(default=""):
                case [lines, "", "A"]:
                    return ANSICursor(delta_y=-int(lines or 1))
                case [lines, "", "B"]:
                    return ANSICursor(delta_y=+int(lines or 1))
                case [cells, "", "C"]:
                    return ANSICursor(delta_x=+int(cells or 1))
                case [cells, "", "D"]:
                    return ANSICursor(delta_x=-int(cells or 1))
                case [lines, "", "E"]:
                    return ANSICursor(absolute_x=0, delta_y=+int(lines or 1))
                case [lines, "", "F"]:
                    return ANSICursor(absolute_x=0, delta_y=-int(lines or 1))
                case [cells, "", "G"]:
                    return ANSICursor(absolute_x=+int(cells or 1) - 1)
                case [row, column, "H"]:
                    return ANSICursor(
                        absolute_x=int(column or 1) - 1,
                        absolute_y=int(row or 1) - 1,
                    )
                case [row, "", "d"]:
                    return ANSICursor(absolute_y=int(row or 1) - 1)
                case ["0" | "", "", "J"]:
                    return cls.CLEAR_SCREEN_CURSOR_TO_END
                case ["1", "", "J"]:
                    return cls.CLEAR_SCREEN_CURSOR_TO_BEGINNING
                case ["2", "", "J"]:
                    return cls.CLEAR_SCREEN
                case ["3", "", "J"]:
                    return cls.CLEAR_SCREEN_SCROLLBACK
                case ["0" | "", "", "K"]:
                    return cls.CLEAR_LINE_CURSOR_TO_END
                case ["1", "", "K"]:
                    return cls.CLEAR_LINE_CURSOR_TO_BEGINNING
                case ["2", "", "K"]:
                    return cls.CLEAR_LINE
                case [top, bottom, "r"]:
                    return ANSIScrollMargin(
                        int(top) if top else None, int(bottom) if bottom else None
                    )
                case _:
                    print("Unknown CSI (a)", repr(csi))
                    return None
        elif match := re.fullmatch(r"\x1b\[([0-9:;<=>?]*)([!-/]*)([@-~])", csi):
            match match.groups(default=""):
                case ["?25", "", "h"]:
                    return cls.SHOW_CURSOR
                case ["?25", "", "l"]:
                    return cls.HIDE_CURSOR
                case ["?1049", "", "h"]:
                    return cls.ENABLE_ALTERNATE_SCREEN
                case ["?1049", "", "l"]:
                    return cls.DISABLE_ALTERNATE_SCREEN
                case _:
                    print("Unknown CSI (b)", repr(csi))
                    return None
        print("Unknown CSI (c)", repr(csi))
        return None

    def on_token(self, token: ANSIToken) -> Iterable[ANSICommand]:
        match token:
            case Separator(separator):
                yield self.ANSI_SEPARATORS[separator]

            case OSC(osc):
                match osc.split(";"):
                    case ["8", *_, link]:
                        self.style += Style(link=link or None)
                    case ["2025", current_directory, *_]:
                        self.current_directory = current_directory
                        yield ANSIWorkingDirectory(current_directory)

            case CSI(csi):
                if csi.endswith("m"):
                    if (sgr_style := self._parse_sgr(csi[2:-1])) is None:
                        self.style = NULL_STYLE
                    else:
                        self.style += sgr_style
                    yield ANSIStyle(self.style)
                else:
                    if (ansi_segment := self._parse_csi(csi)) is not None:
                        yield ansi_segment

            case DEC():
                yield ANSICharacterSet(dec=token)

            case DECInvoke():
                yield ANSICharacterSet(dec_invoke=token)

            case ANSIContent(text):
                yield ANSICursor(delta_x=len(text), text=text)


class LineFold(NamedTuple):
    """A line from the terminal, folded for presentation."""

    line_no: int
    """The (unfolded) line number."""

    line_offset: int
    """The index of the folded line."""

    offset: int
    """The offset within the original line."""

    content: Content
    """The content."""

    updates: int = 0
    """Integer that increments on update."""


@dataclass
class LineRecord:
    """A single line in the terminal."""

    content: Content
    """The content."""

    folds: list[LineFold] = field(default_factory=list)
    """Line "folds" for wrapped lines."""

    updates: int = 0
    """An integer used for caching."""


@dataclass
class Buffer:
    lines: list[LineRecord] = field(default_factory=list)
    """unfolded lines."""

    line_to_fold: list[int] = field(default_factory=list)
    """An index from folded lines on to unfolded lines."""

    folded_lines: list[LineFold] = field(default_factory=list)
    """Folded lines."""

    cursor_line: int = 0
    """Folded line index."""
    cursor_offset: int = 0
    """Folded line offset."""

    max_line_width: int = 0

    updates: int = 0

    @property
    def line_count(self) -> int:
        return len(self.lines)

    @property
    def unfolded_line(self) -> int:
        cursor_folded_line = self.folded_lines[self.cursor_line]
        return cursor_folded_line.line_no

    @property
    def cursor(self) -> tuple[int, int]:
        """The cursor offset within the un-folded lines."""

        if self.cursor_line >= len(self.folded_lines):
            return (len(self.folded_lines), 0)
        cursor_folded_line = self.folded_lines[self.cursor_line]
        cursor_line_offset = cursor_folded_line.line_offset
        line_no = cursor_folded_line.line_no
        line = self.lines[line_no]
        position = 0
        for folded_line_offset, folded_line in enumerate(line.folds):
            if folded_line_offset == cursor_line_offset:
                position += self.cursor_offset
                break
            position += len(folded_line.content)

        return (line_no, position)


@dataclass
class DECState:
    """The (somewhat bonkers) mechanism for switching characters sets pre-unicode."""

    slots: list[str] = field(default_factory=lambda: ["B", "B", "<", "0"])
    gl_slot: int = 0
    gr_slot: int = 2
    shift: int | None = None

    @property
    def gl(self) -> str:
        return self.slots[self.gl_slot]

    @property
    def gr(self) -> str:
        return self.slots[self.gr_slot]

    def update(self, dec: DEC | None, dec_invoke: DECInvoke | None) -> None:
        if dec is not None:
            self.slots[dec.slot] = dec.character_set
        elif dec_invoke is not None:
            if dec_invoke.shift:
                self.shift = dec_invoke.shift
            else:
                if dec_invoke.gl is not None:
                    self.gl_slot = dec_invoke.gl
                elif dec_invoke.gr is not None:
                    self.gr_slot = dec_invoke.gr

    def translate(self, text: str) -> str:
        translate_table: dict[int, str] | None
        first_character: str | None = None
        if self.shift is not None and (
            translate_table := CHARSET_MAP.get(self.slots[self.shift], None)
        ):
            first_character = text[0].translate(translate_table)
            self.shift = None

        if translate_table := CHARSET_MAP.get(self.gl, None):
            text = text.translate(translate_table)
        if first_character is None:
            return text
        return f"{first_character}{text}"


class TerminalState:
    """Abstract terminal state (no renderer)."""

    def __init__(self, width: int = 80, height: int = 24) -> None:
        self._ansi_stream = ANSIStream()
        """ANSI stream processor."""

        self.width = width
        """Width of the terminal."""
        self.height = height
        """Height of the terminal."""

        self.style = Style()
        """The current style."""

        self.show_cursor = True
        """Is the cursor visible?"""
        self.alternate_screen = False
        """Is the terminal in the alternate buffer state?"""

        self.current_directory: str = ""
        """Current working directory."""

        self.scrollback_buffer = Buffer()
        """Scrollbar buffer lines."""
        self.alternate_buffer = Buffer()
        """Alternate buffer lines."""

        self.dec_state = DECState()
        """The DEC (character set) state."""

        self._updates: int = 0

    @property
    def buffer(self) -> Buffer:
        """The buffer (scrollack or alternate)"""
        if self.alternate_screen:
            return self.alternate_buffer
        return self.scrollback_buffer

    def advance_updates(self) -> int:
        """Advance the `updates` integer and return it.

        Returns:
            int: Updates.
        """
        self._updates += 1
        return self._updates

    def update_size(self, width: int | None = None, height: int | None = None) -> None:
        """Update the dimensions of the terminal.

        Args:
            width: New width, or `None` for no change.
            height: New height, or `None` for no change.
        """
        if width is not None:
            self.width = width
        if height is not None:
            self.height = height
        self._reflow()

    def _reflow(self) -> None:
        buffer = self.buffer
        if not buffer.lines:
            return

        # Unfolded cursor position
        cursor_line, cursor_offset = buffer.cursor

        buffer.folded_lines.clear()
        buffer.line_to_fold.clear()
        width = self.width

        for line_no, line_record in enumerate(buffer.lines):
            line_expanded_tabs = line_record.content.expand_tabs(8)
            line_record.folds[:] = self._fold_line(line_no, line_expanded_tabs, width)
            line_record.updates = self.advance_updates()
            buffer.line_to_fold.append(len(buffer.folded_lines))
            buffer.folded_lines.extend(line_record.folds)

        # After reflow, we need to work out where the cursor is within the folded lines
        line = buffer.lines[cursor_line]
        fold_cursor_line = buffer.line_to_fold[cursor_line]

        fold_cursor_offset = 0
        for fold in reversed(line.folds):
            if cursor_offset >= fold.offset:
                fold_cursor_line += fold.line_offset
                fold_cursor_offset = cursor_offset - fold.offset
                break

        buffer.cursor_line = fold_cursor_line
        buffer.cursor_offset = fold_cursor_offset

    def write(self, text: str) -> None:
        """Write to the terminal.

        Args:
            text: Text to write.
        """
        for ansi_command in self._ansi_stream.feed(text):
            self._handle_ansi_command(ansi_command)

    def get_cursor_line_offset(self, buffer: Buffer) -> int:
        """The cursor offset within the un-folded lines."""
        cursor_folded_line = buffer.folded_lines[buffer.cursor_line]
        cursor_line_offset = cursor_folded_line.line_offset
        line_no = cursor_folded_line.line_no
        line = buffer.lines[line_no]
        position = 0
        for folded_line_offset, folded_line in enumerate(line.folds):
            if folded_line_offset == cursor_line_offset:
                position += buffer.cursor_offset
                break
            position += len(folded_line.content)
        return position

    def _handle_ansi_command(self, ansi_command: ANSICommand) -> None:
        print(ansi_command)
        match ansi_command:
            case ANSIStyle(style):
                self.style = style
            case ANSICursor(delta_x, delta_y, absolute_x, absolute_y, text, replace):
                buffer = self.buffer
                folded_lines = buffer.folded_lines
                if buffer.cursor_line >= len(folded_lines):
                    while buffer.cursor_line >= len(folded_lines):
                        self.add_line(buffer, Content())

                folded_line = folded_lines[buffer.cursor_line]
                previous_content = folded_line.content
                line = buffer.lines[folded_line.line_no]

                if text is not None:
                    content = Content.styled(self.dec_state.translate(text), self.style)
                    cursor_line_offset = self.get_cursor_line_offset(buffer)

                    if cursor_line_offset > len(line.content):
                        line.content = line.content.pad_right(
                            cursor_line_offset - len(line.content)
                        )

                    if replace is not None:
                        start_replace, end_replace = ansi_command.get_replace_offsets(
                            cursor_line_offset, len(line.content)
                        )
                        updated_line = Content.assemble(
                            line.content[:start_replace],
                            content,
                            line.content[end_replace + 1 :],
                        )
                        updated_line = updated_line.extend_right(
                            self.width - updated_line.cell_length
                        )
                    else:
                        if cursor_line_offset == len(line.content):
                            updated_line = line.content + content
                        else:
                            updated_line = Content.assemble(
                                line.content[:cursor_line_offset],
                                content,
                                line.content[cursor_line_offset + len(content) :],
                            )

                    self.update_line(buffer, folded_line.line_no, updated_line)
                    if not previous_content.is_same(folded_line.content):
                        buffer.updates = self.advance_updates()

                if delta_x is not None:
                    buffer.cursor_offset += delta_x
                    while buffer.cursor_offset > self.width:
                        buffer.cursor_line += 1
                        buffer.cursor_offset -= self.width
                if absolute_x is not None:
                    buffer.cursor_offset = absolute_x

                current_cursor_line = buffer.cursor_line
                if delta_y is not None:
                    buffer.cursor_line = max(0, buffer.cursor_line + delta_y)
                if absolute_y is not None:
                    buffer.cursor_line = max(0, absolute_y)

                if current_cursor_line != buffer.cursor_line:
                    line.content.simplify()  # Reduce segments
                    self._line_updated(buffer, current_cursor_line)
                    self._line_updated(buffer, buffer.cursor_line)

            case ANSICursorShow(show_cursor):
                self.show_cursor = show_cursor

            case ANSIAlternateScreen(alternate_buffer):
                self.alternate_screen = alternate_buffer
                while len(self.alternate_buffer.lines) < self.height:
                    self.add_line(self.alternate_buffer, EMPTY_LINE)

            case ANSICharacterSet(dec, dec_invoke):
                self.dec_state.update(dec, dec_invoke)

            case ANSIWorkingDirectory(path):
                self.current_directory = path
                # self.finalize()

            case _:
                print("Unhandled", ansi_command)

    def _line_updated(self, buffer: Buffer, line_no: int) -> None:
        """Mark a line has having been udpated.

        Args:
            buffer: Buffer to use.
            line_no: Line number to mark as updated.
        """
        try:
            buffer.lines[line_no].updates = self.advance_updates()
        except IndexError:
            pass

    def _fold_line(self, line_no: int, line: Content, width: int) -> list[LineFold]:
        updates = self.advance_updates()
        if not width:
            return [LineFold(0, 0, 0, line, updates)]
        line_length = line.cell_length
        if line_length <= width:
            return [LineFold(line_no, 0, 0, line, updates)]
        divide_offsets = list(range(width, line_length, width))
        folded_lines = [folded_line for folded_line in line.divide(divide_offsets)]
        offsets = [0, *divide_offsets]
        folds = [
            LineFold(line_no, line_offset, offset, folded_line, updates)
            for line_offset, (offset, folded_line) in enumerate(
                zip(offsets, folded_lines)
            )
        ]
        assert len(folds)
        return folds

    def add_line(self, buffer: Buffer, content: Content) -> None:
        updates = self.advance_updates()
        line_no = buffer.line_count
        width = self.width
        line_record = LineRecord(
            content, self._fold_line(line_no, content, width), updates
        )
        buffer.lines.append(line_record)
        folds = line_record.folds
        buffer.line_to_fold.append(len(buffer.folded_lines))
        buffer.folded_lines.extend(folds)

        buffer.updates = updates

    def update_line(self, buffer: Buffer, line_index: int, line: Content) -> None:
        while line_index >= len(buffer.lines):
            self.add_line(buffer, Content())

        updates = self.advance_updates()

        line_expanded_tabs = line.expand_tabs(8)
        buffer.max_line_width = max(
            line_expanded_tabs.cell_length, buffer.max_line_width
        )

        line_record = buffer.lines[line_index]
        line_record.content = line
        line_record.folds[:] = self._fold_line(
            line_index, line_expanded_tabs, self.width
        )
        line_record.updates = updates

        fold_line = buffer.line_to_fold[line_index]
        del buffer.line_to_fold[line_index:]
        del buffer.folded_lines[fold_line:]

        for line_no in range(line_index, buffer.line_count):
            line_record = buffer.lines[line_no]
            # line_record.updates += 1
            buffer.line_to_fold.append(len(buffer.folded_lines))
            for fold in line_record.folds:
                buffer.folded_lines.append(fold)

        # self.refresh(Region(0, line_index, self._width, refresh_lines))


if __name__ == "__main__":
    from textual.content import Content

    from rich import print

    # content = Content.from_markup(
    #     "Hello\n[bold magenta]World[/]!\n[ansi_red]This is [i]red\nVisit [link='https://www.willmcgugan.com']My blog[/]."
    # )
    content = Content.from_markup(
        "[red]012345678901234567890123455678901234567789[/red] " * 2
    )
    # content = Content.from_markup("[link='https://www.willmcgugan.com']My blog[/].")
    ansi_text = "".join(
        segment.style.render(segment.text) if segment.style else segment.text
        for segment in content.render_segments()
    )
    # print(content)
    # print(repr(ansi_text))

    parser = ANSIStream()
    from itertools import batched

    for batch in batched(ansi_text, 1000):
        for ansi_segment in parser.feed("".join(batch)):
            print(repr(ansi_segment))

    # for line in parser.lines:
    #     print(line)
