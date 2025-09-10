from dataclasses import dataclass

from textual.message import Message


class ACPAgentMessage(Message):
    pass


class ACPThinking(ACPAgentMessage):
    pass


@dataclass
class ACPUpdate(ACPAgentMessage):
    type: str
    text: str
