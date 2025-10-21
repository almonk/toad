from __future__ import annotations


import os
import asyncio
import codecs
import fcntl
import platform
import pty
import struct
import termios
from dataclasses import dataclass
from typing import TYPE_CHECKING
from time import monotonic

from textual.message import Message


from toad.widgets.ansi_log import ANSILog

if TYPE_CHECKING:
    from toad.widgets.conversation import Conversation

IS_MACOS = platform.system() == "Darwin"


def resize_pty(fd, cols, rows):
    """Resize the pseudo-terminal"""
    # Pack the dimensions into the format expected by TIOCSWINSZ
    size = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, size)


@dataclass
class CurrentWorkingDirectoryChanged(Message):
    """Current working directory has changed in shell."""

    path: str


@dataclass
class ShellFinished(Message):
    """The shell finished."""


class Shell:
    def __init__(
        self,
        conversation: Conversation,
        working_directory: str,
        max_buffer_duration: float = 1 / 60,
    ) -> None:
        self.conversation = conversation
        self.working_directory = working_directory
        self.max_buffer_duration = max_buffer_duration

        self.ansi_log: ANSILog | None = None
        self.new_log: bool = False
        self.shell = os.environ.get("SHELL", "sh")
        self.master = 0
        self._task: asyncio.Task | None = None
        self.width = 80
        self.height = 24
        self._process: asyncio.subprocess.Process | None = None
        self.writer: asyncio.WriteTransport | None = None

        self._finished: bool = False
        self._ready_event: asyncio.Event = asyncio.Event()

    @property
    def is_finished(self) -> bool:
        return self._finished

    async def send(self, command: str, width: int, height: int) -> None:
        await self._ready_event.wait()
        height = max(height, 1)
        self.width = width
        self.height = height
        resize_pty(self.master, width, height)
        command = f"{command}\n"
        self.writer.write(command.encode("utf-8"))

        get_pwd_command = r'printf "\e]2025;$(pwd);\e\\"' + "\n"
        self.writer.write(get_pwd_command.encode("utf-8"))
        self.ansi_log = None

    def start(self) -> None:
        assert self._task is None
        self._task = asyncio.create_task(self.run(), name=repr(self))

    async def interrupt(self) -> None:
        """Interrupt the running command."""
        if self.writer is not None:
            self.writer.write(b"\x03")

    async def run(self) -> None:
        current_directory = self.working_directory

        master, slave = pty.openpty()
        self.master = master

        flags = fcntl.fcntl(master, fcntl.F_GETFL)
        fcntl.fcntl(master, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Get terminal attributes
        attrs = termios.tcgetattr(slave)

        # Disable echo (ECHO flag)
        attrs[3] &= ~termios.ECHO
        attrs[0] |= termios.ISIG

        # Apply the changes
        termios.tcsetattr(slave, termios.TCSANOW, attrs)

        env = os.environ.copy()
        env["FORCE_COLOR"] = "1"
        env["TTY_COMPATIBLE"] = "1"
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
        env["TOAD"] = "1"
        env["CLICOLOR"] = "1"
        if IS_MACOS:
            shell = f"{self.shell} +o interactive"
        else:
            shell = self.shell

        _process = await asyncio.create_subprocess_shell(
            shell,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=env,
            cwd=current_directory,
            start_new_session=True,  # Linux / macOS only
        )

        os.close(slave)
        BUFFER_SIZE = 64 * 1024
        reader = asyncio.StreamReader(BUFFER_SIZE)
        protocol = asyncio.StreamReaderProtocol(reader)

        loop = asyncio.get_event_loop()
        transport, _ = await loop.connect_read_pipe(
            lambda: protocol, os.fdopen(master, "rb", 0)
        )

        # Create write transport
        writer_protocol = asyncio.BaseProtocol()
        write_transport, _ = await loop.connect_write_pipe(
            lambda: writer_protocol,
            os.fdopen(os.dup(master), "wb", 0),
        )
        self.writer = write_transport
        if not IS_MACOS:
            self.writer.write(b'set +x\nPS1="";\n')

        unicode_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

        self._ready_event.set()
        try:
            while True:
                data = await reader.read(BUFFER_SIZE)
                if data:
                    buffer_time = monotonic() + self.max_buffer_duration
                    # Accumulate data for a short period of time, or until we have enough data
                    # This can reduce the number of refreshes we need to do
                    # Resulting in faster updates and less flicker.
                    try:
                        while (
                            len(data) < BUFFER_SIZE
                            and (time := monotonic()) < buffer_time
                        ):
                            async with asyncio.timeout(buffer_time - time):
                                data += await reader.read(BUFFER_SIZE)
                    except asyncio.TimeoutError:
                        pass

                if line := unicode_decoder.decode(data, final=not data):
                    if self.ansi_log is None or self.ansi_log.is_finalized:
                        self.ansi_log = await self.conversation.new_ansi_log(
                            self.width, display=False
                        )
                    if self.ansi_log.write(line):
                        self.ansi_log.display = True
                    new_directory = self.ansi_log.current_directory
                    if new_directory and new_directory != current_directory:
                        current_directory = new_directory
                        self.conversation.post_message(
                            CurrentWorkingDirectoryChanged(current_directory)
                        )
                if not data:
                    break

        finally:
            transport.close()
        self.writer = None
        self._finished = True
        self.conversation.post_message(ShellFinished())
