from __future__ import annotations


import os
import asyncio
import codecs
import fcntl
import pty
import struct
import termios


from toad.widgets.ansi_log import ANSILog


def resize_pty(fd, cols, rows):
    """Resize the pseudo-terminal"""
    # Pack the dimensions into the format expected by TIOCSWINSZ
    size = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, size)


class Shell:
    def __init__(self) -> None:
        self.ansi_log: ANSILog | None = None
        self.shell = os.environ.get("SHELL", "sh")
        self.width = 80
        self.height = 24
        self.master = 0
        self._task: asyncio.Task | None = None

    async def send(self, command: str, ansi_log: ANSILog) -> None:
        self.ansi_log = ansi_log
        width = ansi_log.scrollable_content_region.width
        height = 24

        command = f"{command}\n"

        self.writer.write(command.encode("utf-8"))
        resize_pty(self.master, width, height)

    def start(self) -> None:
        self._task = asyncio.create_task(self.run())

    async def run(self) -> None:
        master, slave = pty.openpty()
        self.master = master

        flags = fcntl.fcntl(master, fcntl.F_GETFL)
        fcntl.fcntl(master, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Get terminal attributes
        attrs = termios.tcgetattr(slave)

        # Disable echo (ECHO flag)
        attrs[3] &= ~termios.ECHO

        # Apply the changes
        termios.tcsetattr(slave, termios.TCSANOW, attrs)

        env = os.environ.copy()
        env["PS1"] = ""
        env["PS2"] = ""
        env["PS3"] = ""
        env["PS4"] = ""
        env["RPS1"] = ""
        env["RPS2"] = ""
        env["PROMPT"] = ""
        env["RPROMPT"] = ""
        shell = f"{self.shell} +o interactive"
        process = await asyncio.create_subprocess_shell(
            shell,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=env,
        )

        os.close(slave)

        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)

        loop = asyncio.get_event_loop()
        transport, _ = await loop.connect_read_pipe(
            lambda: protocol, os.fdopen(master, "rb", 0)
        )

        # Create write transport
        writer_protocol = asyncio.BaseProtocol()
        write_transport, _ = await loop.connect_write_pipe(
            lambda: writer_protocol, os.fdopen(os.dup(master), "wb", 0)
        )
        self.writer = write_transport

        unicode_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            while True:
                try:
                    # Read with timeout
                    data = await asyncio.wait_for(reader.read(1024 * 16), timeout=None)
                    # print(repr(data))
                    if not data:
                        break
                    line = unicode_decoder.decode(data)
                    if line and self.ansi_log is not None:
                        self.ansi_log.write(line)
                except asyncio.TimeoutError:
                    # Check if process is still running
                    if process.returncode is not None:
                        break
        finally:
            transport.close()

        line = unicode_decoder.decode(b"", final=True)
        if line and self.ansi_log is not None:
            self.ansi_log.write(line)

        await process.wait()
