from textual.app import ComposeResult
from textual import containers
from textual.widgets import Label
from textual.reactive import var
from textual import getters

from toad.widgets.ansi_log import ANSILog


class RunOutput(ANSILog):
    pass
