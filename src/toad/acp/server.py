from toad.acp.agent import Agent

from toad.jsonrpc import Server


class AgentServer(Server):
    def __init__(self, agent: Agent) -> None:
        self.agent = agent
        super().__init__()
