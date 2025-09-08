from typing import TypedDict, Required


# https://agentclientprotocol.com/protocol/schema#clientcapabilities
class ClientCapabilities(TypedDict, total=False):
    fs: Required[dict[str, bool]]
    terminal: bool


# https://agentclientprotocol.com/protocol/schema#promptcapabilities
class PromptCapabilities(TypedDict):
    audio: bool
    embeddedContent: bool
    image: bool


# https://agentclientprotocol.com/protocol/schema#agentcapabilities
class AgentCapabilities(TypedDict):
    loadSession: bool
    promptCapabilities: PromptCapabilities


class AuthMethod(TypedDict, total=False):
    description: str | None
    id: Required[str]
    name: Required[str]


class InitializeResponse(TypedDict):
    agentCapabilities: AgentCapabilities
    authMethods: list[AuthMethod]
    protocolVersion: Required[int]


class EnvVariable(TypedDict):
    name: str
    value: str


# https://agentclientprotocol.com/protocol/schema#mcpserver
class McpServer(TypedDict):
    args: list[str]
    command: str
    env: list[EnvVariable]
    name: str


class NewSessionResponse(TypedDict):
    sessionID: str
