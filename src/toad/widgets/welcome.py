from textual.app import ComposeResult
from textual import containers

from textual.widgets import Label, Markdown


ASCII_TOAD = r"""
         _   _
        (.)_(.)
     _ (   _   ) _
    / \/`-----'\/ \
  __\ ( (     ) ) /__
  )   /\ \._./ /\   (
   )_/ /|\   /|\ \_(
"""


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


class Welcome(containers.Vertical):
    def compose(self) -> ComposeResult:
        with containers.Center():
            yield Label(ASCII_TOAD, id="logo")
        yield Markdown(WELCOME_MD, id="message")
