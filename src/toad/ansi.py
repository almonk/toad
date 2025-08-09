from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import io
from contextlib import suppress
from typing import Generator, Iterable, NamedTuple
from textual.color import Color
from textual.style import Style, NULL_STYLE
from textual.content import Content

from toad._stream_parser import (
    MatchToken,
    StreamParser,
    SeparatorToken,
    StreamRead,
    Token,
    PatternToken,
    Pattern,
    PatternCheck,
)


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


class OSCPattern(Pattern):
    class Match(NamedTuple):
        code: str

    def check(self) -> PatternCheck:
        if (yield) != "]":
            return False
        return self.Match("]")


SGR_STYLE_MAP: dict[int, Style] = {
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


@dataclass
class ANSIToken:
    text: str


class Separator(ANSIToken):
    pass


@dataclass
class CSI(ANSIToken):
    pass


@dataclass
class OSC(ANSIToken):
    pass


class ANSIParser(StreamParser):
    def parse(self) -> Generator[StreamRead | Token | ANSIToken, Token, None]:
        NEW_LINE = "\n"
        CARRIAGE_RETURN = "\r"
        ESCAPE = "\x1b"

        while True:
            token = yield self.read_until(NEW_LINE, CARRIAGE_RETURN, ESCAPE)

            if isinstance(token, SeparatorToken):
                if token.text == ESCAPE:
                    token = yield self.read_patterns(
                        "\x1b", csi=CSIPattern(), osc=OSCPattern()
                    )

                    if isinstance(token, PatternToken):
                        value = token.value

                        if isinstance(value, CSIPattern.Match):
                            yield CSI(value.full)

                        elif isinstance(value, OSCPattern.Match):
                            osc_data: list[str] = []
                            while True:
                                token = yield self.read_regex(r"[\x1b\0x7]\\")
                                if isinstance(token, MatchToken):
                                    break
                                osc_data.append(token.text)

                            yield OSC("".join(osc_data))
                            continue
                else:
                    yield Separator(token.text)
                continue

            yield ANSIToken(token.text)


EMPTY_LINE = Content()


ANSI_COLORS = [
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


class ANSISegment(NamedTuple):
    delta_x: int = 0
    delta_y: int = 0
    content: Content | None = None


class ANSIStream:
    def __init__(self) -> None:
        self.parser = ANSIParser()
        self.style = Style()

    @classmethod
    @lru_cache(maxsize=1024)
    def parse_sgr(cls, sgr: str) -> Style | None:
        codes = [
            min(255, int(_code) if _code else 0)
            for _code in sgr.split(";")
            if _code.isdigit() or _code == ""
        ]
        style = NULL_STYLE
        iter_codes = iter(codes)
        for code in iter_codes:
            if code == 0:
                # reset
                return None
            elif code in SGR_STYLE_MAP:
                # styles
                style += SGR_STYLE_MAP[code]
            elif code == 38:
                #  Foreground
                with suppress(StopIteration):
                    color_type = next(iter_codes)
                    if color_type == 5:
                        style += Style(
                            foreground=Color.parse(ANSI_COLORS[next(iter_codes)])
                        )
                    elif color_type == 2:
                        style += Style(
                            foreground=Color(
                                next(iter_codes),
                                next(iter_codes),
                                next(iter_codes),
                            )
                        )

            elif code == 48:
                # Background
                with suppress(StopIteration):
                    color_type = next(iter_codes)
                    if color_type == 5:
                        style += Style(
                            background=Color.parse(ANSI_COLORS[next(iter_codes)])
                        )
                    elif color_type == 2:
                        style += Style(
                            background=Color(
                                next(iter_codes),
                                next(iter_codes),
                                next(iter_codes),
                            )
                        )
        return style

    def feed(self, text: str) -> Iterable[ANSISegment]:
        for token in self.parser.feed(text):
            yield from self.on_token(token)

    def on_token(self, token: ANSIToken) -> Iterable[ANSISegment]:
        if isinstance(token, Separator):
            if token.text == "\n":
                yield ANSISegment(0, 1)
            else:
                # TODO: Bell, carriage return etc
                pass

        elif isinstance(token, OSC):
            osc = token.text
            osc_parameters = osc.split(";")
            if osc_parameters:
                if osc_parameters[0] == "8":
                    link = osc_parameters[-1]
                    self.style += Style(link=link or None)

        elif isinstance(token, CSI):
            if token.text.endswith("m"):
                sgr_style = self.parse_sgr(token.text[2:-1])
                if sgr_style is None:
                    self.style = NULL_STYLE
                else:
                    self.style += sgr_style

        else:
            if self.style:
                content = Content.styled(token.text, self.style)
            else:
                content = Content(token.text)
            yield ANSISegment(content.cell_length, 0, content)


if __name__ == "__main__":
    from textual.content import Content

    from rich import print

    content = Content.from_markup(
        "Hello\n[bold magenta]World[/]!\n[ansi_red]This is [i]red\nVisit [link='https://www.willmcgugan.com']My blog[/]."
    )
    # content = Content.from_markup("[link='https://www.willmcgugan.com']My blog[/].")
    ansi_text = "".join(
        segment.style.render(segment.text) if segment.style else segment.text
        for segment in content.render_segments()
    )
    print(content)
    print(repr(ansi_text))

    parser = ANSIStream()
    from itertools import batched

    for batch in batched(ansi_text, 2):
        token = parser.feed("".join(batch))

    print(parser.lines)
    print(parser)

    print(parser.lines)
    # for line in parser.lines:
    #     print(line)
