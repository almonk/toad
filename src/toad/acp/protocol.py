from typing import TypedDict, Required, Literal


class SchemaDict(TypedDict, total=False):
    pass


class FileSystemCapability(SchemaDict, total=False):
    readTextFile: bool
    writeTextFile: bool


# https://agentclientprotocol.com/protocol/schema#clientcapabilities
class ClientCapabilities(SchemaDict, total=False):
    fs: FileSystemCapability
    # terminal: bool


# https://agentclientprotocol.com/protocol/schema#promptcapabilities
class PromptCapabilities(SchemaDict, total=False):
    audio: bool
    embeddedContent: bool
    image: bool


# https://agentclientprotocol.com/protocol/schema#agentcapabilities
class AgentCapabilities(SchemaDict, total=False):
    loadSession: bool
    promptCapabilities: PromptCapabilities


class AuthMethod(SchemaDict, total=False):
    description: str | None
    id: Required[str]
    name: Required[str]


class InitializeResponse(SchemaDict, total=False):
    agentCapabilities: AgentCapabilities
    authMethods: list[AuthMethod]
    protocolVersion: Required[int]


class EnvVariable(SchemaDict, total=False):
    name: str
    value: str


# https://agentclientprotocol.com/protocol/schema#mcpserver
class McpServer(SchemaDict, total=False):
    args: list[str]
    command: str
    env: list[EnvVariable]
    name: str


class NewSessionResponse(SchemaDict, total=False):
    sessionId: Required[str]


# https://modelcontextprotocol.io/specification/2025-06-18/server/resources#annotations
class Annotations(SchemaDict, total=False):
    audience: list[str]
    priority: float
    lastModified: str


class TextContent(SchemaDict, total=False):
    type: Required[str]
    text: Required[str]
    annotations: Annotations


class ImageContent(SchemaDict, total=False):
    type: Required[str]
    data: Required[str]
    mimeType: Required[str]
    url: str
    annotations: Annotations


class AudioContent(SchemaDict, total=False):
    type: Required[str]
    data: Required[str]
    mimeType: Required[str]
    Annotations: Annotations


class EmbeddedResourceText(SchemaDict, total=False):
    uri: Required[str]
    text: Required[str]
    mimeType: str


class EmbeddedResourceBlob(SchemaDict, total=False):
    uri: Required[str]
    blob: Required[str]
    mimeType: str


# https://agentclientprotocol.com/protocol/content#embedded-resource
class EmbeddedResourceContent(SchemaDict, total=False):
    type: Required[str]
    resource: EmbeddedResourceText | EmbeddedResourceBlob


class ResourceLinkContent(SchemaDict, total=False):
    annotations: Annotations | None
    description: str | None
    mimeType: str | None
    name: Required[str]
    size: int | None
    title: str | None
    type: Required[str]
    uri: Required[str]


type ContentBlock = (
    TextContent
    | ImageContent
    | AudioContent
    | EmbeddedResourceContent
    | ResourceLinkContent
)


# https://agentclientprotocol.com/protocol/schema#param-user-message-chunk
class UserMessageChunk(SchemaDict, total=False):
    content: Required[ContentBlock]
    sessionUpdate: Required[Literal["user_message_chunk"]]


class AgentMessageChunk(SchemaDict, total=False):
    content: Required[ContentBlock]
    sessionUpdate: Required[Literal["agent_message_chunk"]]


class AgentThoughtChunk(SchemaDict, total=False):
    content: Required[ContentBlock]
    sessionUpdate: Required[Literal["agent_thought_chunk"]]


class ToolCallContentContent(SchemaDict, total=False):
    content: Required[ContentBlock]
    type: Required[str]


class ToolCallContentDiff(SchemaDict, total=False):
    newText: Required[str]
    oldText: str
    path: Required[str]
    type: Required[str]


class ToolCallContentTerminal(SchemaDict, total=False):
    terminalId: Required[str]
    type: Required[str]


# https://agentclientprotocol.com/protocol/schema#toolcallcontent
type ToolCallContent = (
    ToolCallContentContent | ToolCallContentDiff | ToolCallContentTerminal
)

# https://agentclientprotocol.com/protocol/schema#toolkind
type ToolKind = Literal[
    "read",
    "edit",
    "delete",
    "move",
    "search",
    "execute",
    "think",
    "fetch",
    "switch_mode",
    "other",
]

type ToolCallStatus = Literal["pending", "in_progress", "completed", "failed"]


class ToolCallLocation(SchemaDict, total=False):
    line: int | None
    path: Required[str]


type ToolCallId = str


class ToolCall(SchemaDict, total=False):
    content: list[ToolCallContent]
    kind: ToolKind
    locations: list[ToolCallLocation]
    rawInput: dict
    rawOutput: dict
    sessionUpdate: Required[Literal["tool_call"]]
    status: ToolCallStatus
    title: str
    toolCallId: Required[ToolCallId]


class ToolCallUpdate(SchemaDict, total=False):
    content: list | None
    kind: ToolKind | None
    locations: list | None
    rawInput: dict
    rawOutput: dict
    sessionUpdate: Required[Literal["tool_call_update"]]
    status: ToolCallStatus | None
    title: str | None
    toolCallId: ToolCallId


class PlanEntry(SchemaDict, total=False):
    content: Required[str]
    priority: Literal["high", "medium", "low"]
    status: Literal["pending", "in_progress", "completed"]


# https://agentclientprotocol.com/protocol/schema#param-plan
class Plan(SchemaDict, total=False):
    entries: Required[list[PlanEntry]]
    sessionUpdate: Required[Literal["plan"]]


class AvailableCommandInput(SchemaDict, total=False):
    hint: Required[str]


class AvailableCommand(SchemaDict, total=False):
    description: Required[str]
    input: AvailableCommandInput | None
    name: Required[str]


class AvailableCommandsUpdate(SchemaDict, total=False):
    availableCommands: Required[list[AvailableCommand]]
    sessionUpdate: Required[Literal["available_commands_update"]]


class CurrentModeUpdate(SchemaDict, total=False):
    currentModeId: Required[str]
    sessionUpdate: Required[Literal["current_mode_update"]]


type SessionUpdate = (
    UserMessageChunk
    | AgentMessageChunk
    | AgentThoughtChunk
    | ToolCall
    | ToolCallUpdate
    | Plan
    | AvailableCommandsUpdate
    | CurrentModeUpdate
)


class SessionNotification(TypedDict, total=False):
    sessionId: str
    update: SessionUpdate
