import asyncio
import json
import os
from pathlib import Path

from logging import getLogger

from textual.content import Content
from textual.message_pump import MessagePump

from toad import jsonrpc
from toad.agent import AgentBase
from toad.acp import protocol
from toad.acp import api
from toad.acp.api import API
from toad.acp import messages
from toad.acp.prompt import build as build_prompt

log = getLogger("acp")

PROTOCOL_VERSION = 1


class Agent(AgentBase):
    """An agent that speaks the APC (https://agentclientprotocol.com/overview/introduction) protocol."""

    def __init__(self, project_root: Path, command: str) -> None:
        """

        Args:
            project_root: Project root path.
            command: Command to launch agent.
        """
        super().__init__(project_root)

        self.command = command

        self.server = jsonrpc.Server()
        self.server.expose_instance(self)

        self._agent_task: asyncio.Task | None = None
        self._task: asyncio.Task | None = None
        self._process: asyncio.subprocess.Process | None = None
        self.done_event = asyncio.Event()

        self.agent_capabilities: protocol.AgentCapabilities = {
            "loadSession": False,
            "promptCapabilities": {
                "audio": False,
                "embeddedContent": False,
                "image": False,
            },
        }
        self.auth_methods: list[protocol.AuthMethod] = []
        self.session_id: str = ""

        self._message_target: MessagePump | None = None

    def get_info(self) -> Content:
        return Content(self.command)

    def start(self, message_target: MessagePump | None = None) -> None:
        """Start the agent."""
        self._message_target = message_target
        self._agent_task = asyncio.create_task(self._run_agent())

    def send(self, request: jsonrpc.Request) -> None:
        """Send a request to the agent.

        This is called automatically, if you go through `self.request`.

        Args:
            request: JSONRPC request object.

        """
        assert self._process is not None, "Process should be present here"

        if (stdin := self._process.stdin) is not None:
            stdin.write(b"%s\n" % request.body_json)

    def request(self) -> jsonrpc.Request:
        """Create a request object."""
        return API.request(self.send)

    @jsonrpc.expose("update", prefix="session/")
    def rpc_session_update(self, sessionId: str, update: protocol.SessionUpdate):
        """Agent requests an update.

        https://agentclientprotocol.com/protocol/schema
        """
        message_target = self._message_target
        if message_target is None:
            return
        match update:
            case {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": type, "text": text},
            }:
                message_target.post_message(messages.ACPUpdate(type, text))
            case {
                "sessionUpdate": "agent_thought_chunk",
                "content": {"type": type, "text": text},
            }:
                message_target.post_message(messages.ACPThinking())

    async def _run_agent(self) -> None:
        """Task to communicate with the agent subprocess."""

        PIPE = asyncio.subprocess.PIPE
        process = self._process = await asyncio.create_subprocess_shell(
            self.command,
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE,
            env=os.environ,
        )

        self._task = asyncio.create_task(self.run())

        assert process.stdout is not None
        assert process.stdin is not None

        async def handle_response_object(response: jsonrpc.JSONObject) -> None:
            if "result" in response or "error" in response:
                API.process_response(response)
            elif "method" in response:
                await self.server.call(response)

        while line := await process.stdout.readline():
            # This line should contain JSON, which may be:
            #   A) a JSONRPC request
            #   B) a JSONRPC response to a previous request
            try:
                agent_data = json.loads(line.decode("utf-8"))
                print("IN", agent_data)
            except Exception:
                # TODO: handle this
                raise
            if isinstance(agent_data, dict):
                await handle_response_object(agent_data)
            elif isinstance(agent_data, list):
                for response_object in agent_data:
                    if isinstance(response_object, dict):
                        await handle_response_object(response_object)

        print("exit")

    async def run(self) -> None:
        """The main logic of the Agent."""
        # Boilerplate to initialize comms
        await self.acp_initialize()
        # Create a new session
        await self.acp_new_session()

    async def send_prompt(self, prompt: str) -> None:
        """Send a prompt to the agent.

        !!! note
            This method blocks as it may defer to a thread to read resources.

        Args:
            prompt: Prompt text.
        """
        prompt_content_blocks = await asyncio.to_thread(
            build_prompt, self.project_root_path, prompt
        )
        await self.acp_session_prompt(prompt_content_blocks)

    async def acp_initialize(self):
        """Initialize agent."""
        with self.request():
            initialize_response = api.initialize(
                PROTOCOL_VERSION,
                {
                    "fs": {
                        "readTextFile": True,
                        "writeTextFile": True,
                    }
                },
            )
        response = await initialize_response.wait()
        # Store agents capabilities
        if agent_capabilities := response.get("agentCapabilities"):
            self.agent_capabilities = agent_capabilities
        if auth_methods := response.get("authMethods"):
            self.auth_methods = auth_methods

    async def acp_new_session(self) -> None:
        """Create a new session."""
        with self.request():
            session_new_response = api.session_new(
                str(self.project_root_path),
                [],
            )
        response = await session_new_response.wait()
        self.session_id = response["sessionId"]

    async def acp_session_prompt(self, prompt: list[protocol.ContentBlock]) -> None:
        with self.request():
            api.session_prompt(prompt, self.session_id)


if __name__ == "__main__":
    from rich import print

    async def run_agent():
        agent = Agent(Path("./"), "gemini --experimental-acp")
        print(agent)
        agent.start()
        await agent.done_event.wait()

    asyncio.run(run_agent())
