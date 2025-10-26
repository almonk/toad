from typing import TypedDict

import asyncio

import json
from pathlib import Path

from time import time


class HistoryEntry(TypedDict):
    """An entry in the history file."""

    input: str
    shell: bool
    timestamp: float


class History:
    """Manages a history file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lines: list[str] = []
        self._opened: bool = False

    async def open(self) -> bool:
        """Open the history file, read initial lines.

        Returns:
            `True` if lines were read, otherwise `False`.
        """

        def read_history() -> bool:
            try:
                with self.path.open("r") as history_file:
                    self._lines = history_file.readlines()
            except Exception:
                return False
            return True

        self._opened = await asyncio.to_thread(read_history)
        return self._opened

    async def append(self, input: str, shell: bool) -> bool:
        """Append a history entry.

        Args:
            text: Text in the history.
            shell: Boolean that indicates if the text is shell (`True`) or prompt (`False`).

        Returns:
            `True` on success.
        """

        def write_line() -> bool:
            """Append a line to the history.

            Returns:
                `True` on success, `False` if write failed.
            """
            history_entry: HistoryEntry = {
                "input": input,
                "shell": shell,
                "timestamp": time(),
            }
            line = json.dumps(history_entry)
            self._lines.append(line)
            try:
                with self.path.open("a") as history_file:
                    history_file.write(f"{line}\n")
            except Exception:
                return False
            return True

        if not self._opened:
            await self.open()

        return await asyncio.to_thread(write_line)

    async def get_entry(self, index: int) -> HistoryEntry:
        """Get a history entry via its index.

        Args:
            index: Index of entry (supports negative indexing).

        Returns:
            A history entry dict.
        """
        if not self._opened:
            await self.open()
        try:
            entry_line = self._lines[index]
        except IndexError:
            raise IndexError(f"No history entry at index {index}")
        history_entry: HistoryEntry = json.loads(entry_line)
        return history_entry
