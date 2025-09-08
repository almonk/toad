"""
ACP remote API
"""

from toad import jsonrpc
from toad.acp import protocol

API = jsonrpc.API()


@API.method()
def initialize(
    protocolVersion: int, clientCapabilities: protocol.ClientCapabilities
) -> protocol.InitializeResponse: ...


@API.method(name="new", prefix="session/")
def session_new(
    cwd: str, mcpServers: list[protocol.McpServer]
) -> protocol.NewSessionResponse: ...
