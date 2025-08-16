import asyncio

from llm import Model, Conversation

from textual.reactive import var
from textual import work
from textual.widget import Widget
from textual.widgets import Markdown
from textual.widgets.markdown import MarkdownStream
from toad import messages

SYSTEM = """\
If asked to output code add inline documentation in the google style format, and always use type hinting where appropriate.
Avoid using external libraries where possible, and favor code that writes output to the terminal.
When asked for a table do not wrap it in a code fence.
"""


class AgentResponse(Markdown):
    block_cursor_offset = var(-1)

    def __init__(self, conversation: Conversation, markdown: str | None = None) -> None:
        self.conversation = conversation
        super().__init__(markdown)

    def block_cursor_clear(self) -> None:
        self.block_cursor_offset = -1

    def block_cursor_up(self) -> Widget | None:
        self.log(self, self.children, self.block_cursor_offset)
        if self.block_cursor_offset == -1:
            if self.children:
                self.block_cursor_offset = len(self.children) - 1
            else:
                return None
        else:
            self.block_cursor_offset -= 1

        if self.block_cursor_offset == -1:
            return None
        try:
            return self.children[self.block_cursor_offset]
        except IndexError:
            self.block_cursor_offset = -1
            return None

    def block_cursor_down(self) -> Widget | None:
        if self.block_cursor_offset == -1:
            if self.children:
                self.block_cursor_offset = 0
            else:
                return None
        else:
            self.block_cursor_offset += 1
        if self.block_cursor_offset >= len(self.children):
            self.block_cursor_offset = -1
            return None
        try:
            return self.children[self.block_cursor_offset]
        except IndexError:
            self.block_cursor_offset = -1
            return None

    def get_cursor_block(self) -> Widget | None:
        if self.block_cursor_offset == -1:
            return None
        return self.children[self.block_cursor_offset]

    def block_select(self, widget: Widget) -> None:
        self.block_cursor_offset = self.children.index(widget)

    @work
    async def send_prompt(self, prompt: str) -> None:
        stream = Markdown.get_stream(self)
        try:
            await self._send_prompt(stream, prompt).wait()
        finally:
            await stream.stop()

    @work(thread=True)
    def _send_prompt(self, stream: MarkdownStream, prompt: str) -> None:
        """Get the response in a thread."""
        self.post_message(messages.WorkStarted())
        try:
            llm_response = self.conversation.prompt(prompt, system=SYSTEM)
            for chunk in llm_response:
                self.app.call_from_thread(stream.write, chunk)
        finally:
            self.post_message(messages.WorkFinished())
