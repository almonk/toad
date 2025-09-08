import asyncio
import json
import os
from pathlib import Path
from typing import Callable

from logging import getLogger

from toad import jsonrpc
from toad.acp import protocol
from toad.acp import api
from toad.acp.api import API

log = getLogger("acp")

PROTOCOL_VERSION = 1


def expose(name: str = "", prefix: str = ""):
    def expose_method[T: Callable](callable: T) -> T:
        callable._jsonrpc_expose = f"{prefix}{callable.__name__ or name}"
        return callable

    return expose_method


class Agent:
    def __init__(self, command: str) -> None:
        self.command = command
        self.project_path = Path("./")
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
        self.server = jsonrpc.Server()
        for method_name in dir(self):
            method = getattr(self, method_name)
            if (jsonrpc_expose := getattr(method, "_jsonrpc_expose", None)) is not None:
                self.server.method(jsonrpc_expose)(method)

    def start(self) -> None:
        self._agent_task = asyncio.create_task(self.run_client())

    def send(self, request: jsonrpc.Request) -> None:
        if self._process is None:
            raise RuntimeError("No process")
        stdin = self._process.stdin
        if stdin is not None:
            stdin.write(b"%s\n" % request.body_json)

    def request(self) -> jsonrpc.Request:
        return API.request(self.send)

    @expose()
    def greet(self, name: str) -> str:
        print("Called greet!")
        return f"Hello, {name}!"

    async def run_client(self) -> None:
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
            response = json.loads(line.decode("utf-8"))

            if isinstance(response, dict):
                await handle_response_object(response)
            elif isinstance(response, list):
                for response_object in response:
                    if isinstance(response_object, dict):
                        await handle_response_object(response_object)

        print("exit")

    async def run(self) -> None:
        # result = await self.server.call(
        #     {"jsonrpc": "2.0", "method": "greet", "params": {"name": "Will"}, "id": 0}
        # )
        # print(result)
        await self.acp_initialize()
        await self.acp_new_session()

    async def acp_initialize(self):
        with self.request():
            initialize_response = api.initialize(
                PROTOCOL_VERSION,
                {
                    "fs": {
                        "readTextFile": True,
                        "writeTextFile": True,
                    },
                    "terminal": False,
                },
            )
        response = await initialize_response.wait()
        print("GOT RESPONSE")
        print(response)
        self.agent_capabilities = response["agentCapabilities"]
        self.auth_methods = response["authMethods"]

    async def acp_new_session(self) -> None:
        with self.request():
            session_new_response = api.session_new(str(self.project_path), [])
        response = await session_new_response.wait()
        print("NEW SESSION")
        print(response)
        self.session_id = response["sessionID"]


if __name__ == "__main__":
    from rich import print

    async def run_agent():
        agent = Agent("gemini --experimental-acp")
        agent.start()
        await agent.done_event.wait()

    asyncio.run(run_agent())
