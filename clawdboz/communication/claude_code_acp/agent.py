"""
Claude ACP Agent - Bridges Claude Agent SDK with ACP protocol.

This module implements the ACP Agent interface, converting Claude SDK
messages to ACP session updates for bidirectional communication.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine
from uuid import uuid4

from acp import (
    Agent,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    SetSessionModeResponse,
    start_tool_call,
    text_block,
    update_agent_message,
    update_agent_thought,
    update_tool_call,
)
from acp.interfaces import Client
from acp.schema import (
    AgentCapabilities,
    AudioContentBlock,
    AvailableCommand,
    AvailableCommandInput,
    ClientCapabilities,
    EmbeddedResourceContentBlock,
    HttpMcpServer,
    ImageContentBlock,
    Implementation,
    McpServerStdio,
    ModelInfo,
    PermissionOption,
    PromptCapabilities,
    ResourceContentBlock,
    SessionCapabilities,
    SessionModelState,
    SseMcpServer,
    TextContentBlock,
)
from acp.helpers import update_available_commands

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    Message,
    PermissionMode,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolPermissionContext,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from claude_agent_sdk.types import StreamEvent

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """Represents an active Claude session."""

    session_id: str
    cwd: str
    permission_mode: PermissionMode = "default"
    cancelled: bool = False
    tool_use_cache: dict[str, ToolUseBlock] = field(default_factory=dict)
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    system_prompt: str | dict | None = None
    # Model to use for this session
    model: str | None = None
    # Keep client alive for multi-turn conversations
    client: ClaudeSDKClient | None = None
    client_started: bool = False
    # Track streamed text to avoid duplicate sends
    streamed_text: str = ""
    # Server info from get_server_info() - contains commands, models, etc.
    server_info: dict[str, Any] | None = None


class ClaudeAcpAgent(Agent):
    """
    ACP Agent implementation that bridges Claude Agent SDK with ACP protocol.

    This agent:
    1. Receives ACP requests from clients (Zed, Neovim, etc.)
    2. Converts them to Claude Agent SDK format
    3. Streams Claude responses back as ACP session updates
    4. Handles bidirectional communication (permissions, file ops, etc.)
    """

    def __init__(self) -> None:
        self._conn: Client | None = None
        self._sessions: dict[str, Session] = {}
        self._on_result: Callable[[ResultMessage], Coroutine[Any, Any, None]] | None = None
        # 由 ClaudeClient 設定，用於在工具執行前注入/修改參數
        self._tool_input_transform: (
            Callable[[str, dict[str, Any]], Coroutine[Any, Any, dict[str, Any] | None]] | None
        ) = None

    def on_connect(self, conn: Client) -> None:
        """Called when an ACP client connects."""
        self._conn = conn
        logger.info("ACP client connected")

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        """Handle ACP initialize request."""
        logger.info(f"Initialize request from {client_info}")

        return InitializeResponse(
            protocol_version=protocol_version,
            agent_capabilities=AgentCapabilities(
                prompt_capabilities=PromptCapabilities(
                    image=True,
                    embedded_context=True,
                ),
                session_capabilities=SessionCapabilities(
                    fork={},
                    list={},
                    resume={},
                ),
            ),
            agent_info=Implementation(
                name="claude-code-acp-py",
                title="Claude Code (Python)",
                version="0.1.0",
            ),
            auth_methods=[
                {
                    "id": "claude-login",
                    "name": "Log in with Claude Code",
                    "description": "Run `claude /login` in the terminal",
                }
            ],
        )

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio],
        system_prompt: str | dict | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        """Create a new Claude session."""
        import asyncio

        session_id = str(uuid4())

        # Convert ACP MCP servers to Claude SDK format
        sdk_mcp_servers = self._convert_mcp_servers(mcp_servers)

        # Create a temporary client to get server info (commands, models)
        server_info = await self._get_server_info(cwd, sdk_mcp_servers, system_prompt)

        self._sessions[session_id] = Session(
            session_id=session_id,
            cwd=cwd,
            mcp_servers=sdk_mcp_servers,
            system_prompt=system_prompt,
            server_info=server_info,
        )

        logger.info(f"New session created: {session_id} in {cwd} with {len(sdk_mcp_servers)} MCP servers")

        # Build models state from server_info
        models_state = self._build_models_state(server_info)

        # Schedule sending AvailableCommandsUpdate after returning response
        # (similar to TypeScript's setTimeout approach)
        if self._conn is not None and server_info:
            asyncio.create_task(self._send_available_commands(session_id, server_info))

        return NewSessionResponse(
            session_id=session_id,
            models=models_state,
            modes={
                "current_mode_id": "default",
                "available_modes": [
                    {
                        "id": "default",
                        "name": "Default",
                        "description": "Standard behavior, prompts for dangerous operations",
                    },
                    {
                        "id": "acceptEdits",
                        "name": "Accept Edits",
                        "description": "Auto-accept file edit operations",
                    },
                    {
                        "id": "plan",
                        "name": "Plan Mode",
                        "description": "Planning mode, no actual tool execution",
                    },
                    {
                        "id": "bypassPermissions",
                        "name": "Bypass Permissions",
                        "description": "Bypass all permission checks",
                    },
                ],
            },
        )

    async def set_session_mode(
        self, mode_id: str, session_id: str, **kwargs: Any
    ) -> SetSessionModeResponse | None:
        """Change the permission mode for a session."""
        if session_id not in self._sessions:
            raise ValueError(f"Session not found: {session_id}")

        valid_modes = ["default", "acceptEdits", "plan", "bypassPermissions", "dontAsk"]
        if mode_id not in valid_modes:
            raise ValueError(f"Invalid mode: {mode_id}")

        self._sessions[session_id].permission_mode = mode_id  # type: ignore
        logger.info(f"Session {session_id} mode changed to {mode_id}")

        return SetSessionModeResponse()

    async def prompt(
        self,
        prompt: list[
            TextContentBlock
            | ImageContentBlock
            | AudioContentBlock
            | ResourceContentBlock
            | EmbeddedResourceContentBlock
        ],
        session_id: str,
        **kwargs: Any,
    ) -> PromptResponse:
        """
        Handle a prompt from the ACP client.

        This is the main method that:
        1. Converts ACP prompt to Claude format
        2. Streams Claude responses via ClaudeSDKClient
        3. Converts Claude messages to ACP updates
        """
        if session_id not in self._sessions:
            raise ValueError(f"Session not found: {session_id}")

        session = self._sessions[session_id]
        session.cancelled = False
        session.streamed_text = ""  # Reset for new turn

        # Convert ACP prompt to text
        prompt_text = self._convert_prompt_to_text(prompt)

        logger.info(f"Prompt for session {session_id}: {prompt_text[:100]}...")

        # Build Claude options with MCP servers and permission callback
        # Use --strict-mcp-config when MCP servers are provided to ensure only
        # the specified servers are loaded (ignoring user/project configs)
        extra_args = {}
        if session.mcp_servers:
            extra_args["strict-mcp-config"] = None

        options = ClaudeAgentOptions(
            cwd=session.cwd,
            permission_mode=session.permission_mode,
            include_partial_messages=True,
            mcp_servers=session.mcp_servers if session.mcp_servers else {},
            system_prompt=session.system_prompt,
            model=session.model,
            extra_args=extra_args,
        )

        # Add permission callback if not bypassing permissions
        if session.permission_mode != "bypassPermissions":
            options = ClaudeAgentOptions(
                cwd=session.cwd,
                permission_mode=session.permission_mode,
                include_partial_messages=True,
                mcp_servers=session.mcp_servers if session.mcp_servers else {},
                system_prompt=session.system_prompt,
                model=session.model,
                extra_args=extra_args,
                can_use_tool=self._create_permission_handler(session_id),
            )

        try:
            # Reuse existing client for multi-turn conversations, or create new one
            if session.client is None or not session.client_started:
                session.client = ClaudeSDKClient(options)
                await session.client.__aenter__()
                session.client_started = True
                logger.info(f"Created new ClaudeSDKClient for session {session_id}")

            client = session.client

            # Send the query
            await client.query(prompt_text)

            # Receive and process messages
            async for message in client.receive_response():
                if session.cancelled:
                    await client.interrupt()
                    return PromptResponse(stop_reason="cancelled")

                await self._handle_message(session_id, message)

        except Exception as e:
            logger.error(f"Error in prompt: {e}")
            # On error, close the client so next prompt creates a fresh one
            if session.client and session.client_started:
                try:
                    await session.client.__aexit__(None, None, None)
                except Exception:
                    pass
                session.client = None
                session.client_started = False
            raise

        return PromptResponse(stop_reason="end_turn")

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        """Cancel the current operation for a session."""
        if session_id in self._sessions:
            self._sessions[session_id].cancelled = True
            logger.info(f"Session {session_id} cancelled")

    # --- Conversion Methods ---

    def _convert_prompt_to_text(
        self,
        prompt: list[
            TextContentBlock
            | ImageContentBlock
            | AudioContentBlock
            | ResourceContentBlock
            | EmbeddedResourceContentBlock
        ],
    ) -> str:
        """Convert ACP prompt blocks to text for Claude."""
        parts = []

        for block in prompt:
            if isinstance(block, dict):
                block_type = block.get("type")
                if block_type == "text":
                    parts.append(block.get("text", ""))
                elif block_type == "resource":
                    resource = block.get("resource", {})
                    if "text" in resource:
                        uri = resource.get("uri", "unknown")
                        parts.append(f"\n<context ref=\"{uri}\">\n{resource['text']}\n</context>")
                elif block_type == "resource_link":
                    uri = block.get("uri", "")
                    name = block.get("name", uri.split("/")[-1])
                    parts.append(f"[@{name}]({uri})")
            elif hasattr(block, "text"):
                parts.append(block.text)

        return "\n".join(parts)

    def _convert_mcp_servers(
        self,
        acp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio],
    ) -> dict[str, Any]:
        """Convert ACP MCP server configs to Claude SDK format."""
        sdk_servers: dict[str, Any] = {}

        for i, server in enumerate(acp_servers):
            name = f"mcp-server-{i}"

            # Check for ACP schema types first (Pydantic models)
            if isinstance(server, McpServerStdio):
                name = server.name or name
                # Convert EnvVariable list to dict
                env_dict = {}
                if server.env:
                    for ev in server.env:
                        env_dict[ev.name] = ev.value
                sdk_servers[name] = {
                    "type": "stdio",
                    "command": server.command,
                    "args": server.args or [],
                    "env": env_dict,
                }
                logger.info(f"Added MCP server: {name} (stdio)")

            elif isinstance(server, SseMcpServer):
                name = server.name or name
                server_cfg: dict = {
                    "type": "sse",
                    "url": server.url,
                }
                if server.headers:
                    server_cfg["headers"] = {
                        h.name: h.value for h in server.headers
                    }
                sdk_servers[name] = server_cfg
                logger.info(f"Added MCP server: {name} (sse)")

            elif isinstance(server, HttpMcpServer):
                name = server.name or name
                server_cfg = {
                    "type": "http",
                    "url": server.url,
                }
                if server.headers:
                    server_cfg["headers"] = {
                        h.name: h.value for h in server.headers
                    }
                sdk_servers[name] = server_cfg
                logger.info(f"Added MCP server: {name} (http)")

            elif isinstance(server, dict):
                # Dict-based config (legacy support)
                server_type = server.get("type", "stdio")
                name = server.get("name", name)

                if server_type == "stdio":
                    sdk_servers[name] = {
                        "type": "stdio",
                        "command": server.get("command", ""),
                        "args": server.get("args", []),
                        "env": server.get("env", {}),
                    }
                elif server_type == "sse":
                    server_cfg = {
                        "type": "sse",
                        "url": server.get("url", ""),
                    }
                    if server.get("headers"):
                        server_cfg["headers"] = server["headers"]
                    sdk_servers[name] = server_cfg
                elif server_type == "http":
                    server_cfg = {
                        "type": "http",
                        "url": server.get("url", ""),
                    }
                    if server.get("headers"):
                        server_cfg["headers"] = server["headers"]
                    sdk_servers[name] = server_cfg

                logger.info(f"Added MCP server: {name} ({server_type})")

        return sdk_servers

    async def _handle_message(self, session_id: str, message: Message) -> None:
        """Convert and emit a Claude message as ACP updates."""
        if self._conn is None:
            return

        session = self._sessions.get(session_id)
        if session is None:
            return

        if isinstance(message, AssistantMessage):
            await self._handle_assistant_message(session_id, message, session)

        elif isinstance(message, StreamEvent):
            await self._handle_stream_event(session_id, message)

        elif isinstance(message, SystemMessage):
            # System messages (init, status, etc.) - log but don't emit
            logger.debug(f"System message: {message.subtype}")

        elif isinstance(message, ResultMessage):
            # Result message - session complete
            logger.info(f"Session {session_id} completed: {message.subtype}")
            if self._on_result is not None:
                await self._on_result(message)

        elif isinstance(message, UserMessage):
            # User messages may contain tool results
            await self._handle_user_message(session_id, message, session)

    async def _handle_assistant_message(
        self, session_id: str, message: AssistantMessage, session: Session
    ) -> None:
        """Handle an assistant message from Claude."""
        if self._conn is None:
            return

        for block in message.content:
            if isinstance(block, TextBlock):
                # Skip if this text was already sent via streaming
                if session.streamed_text and block.text == session.streamed_text:
                    # Clear streamed_text for next turn
                    session.streamed_text = ""
                    continue
                # If partially streamed, only send the remaining part
                if session.streamed_text and block.text.startswith(session.streamed_text):
                    remaining = block.text[len(session.streamed_text):]
                    session.streamed_text = ""
                    if remaining:
                        await self._conn.session_update(
                            session_id,
                            update_agent_message(text_block(remaining)),
                        )
                    continue
                # Clear any streamed text and send full message
                session.streamed_text = ""
                await self._conn.session_update(
                    session_id,
                    update_agent_message(text_block(block.text)),
                )

            elif isinstance(block, ThinkingBlock):
                # Thinking/reasoning content
                await self._conn.session_update(
                    session_id,
                    update_agent_thought(text_block(block.thinking)),
                )

            elif isinstance(block, ToolUseBlock):
                # Tool invocation
                session.tool_use_cache[block.id] = block

                await self._conn.session_update(
                    session_id,
                    start_tool_call(
                        tool_call_id=block.id,
                        title=self._get_tool_title(block.name, block.input),
                        status="pending",
                        raw_input=block.input,
                    ),
                )

            elif isinstance(block, ToolResultBlock):
                # Tool result
                status = "failed" if block.is_error else "completed"

                await self._conn.session_update(
                    session_id,
                    update_tool_call(
                        tool_call_id=block.tool_use_id,
                        status=status,
                        raw_output=block.content,
                    ),
                )

    async def _handle_user_message(
        self, session_id: str, message: UserMessage, session: Session
    ) -> None:
        """Handle a user message (which may contain tool results)."""
        if self._conn is None:
            return

        for block in message.content:
            if isinstance(block, ToolResultBlock):
                # Tool result
                status = "failed" if block.is_error else "completed"

                await self._conn.session_update(
                    session_id,
                    update_tool_call(
                        tool_call_id=block.tool_use_id,
                        status=status,
                        raw_output=block.content,
                    ),
                )

    async def _handle_stream_event(self, session_id: str, event: StreamEvent) -> None:
        """Handle a streaming event from Claude."""
        if self._conn is None:
            return

        event_data = event.event
        event_type = event_data.get("type")

        if event_type == "content_block_delta":
            delta = event_data.get("delta", {})
            delta_type = delta.get("type")

            if delta_type == "text_delta":
                text = delta.get("text", "")
                if text:
                    # Track streamed text to avoid duplicate in _handle_message
                    if session_id in self._sessions:
                        self._sessions[session_id].streamed_text += text
                    await self._conn.session_update(
                        session_id,
                        update_agent_message(text_block(text)),
                    )

            elif delta_type == "thinking_delta":
                thinking = delta.get("thinking", "")
                if thinking:
                    await self._conn.session_update(
                        session_id,
                        update_agent_thought(text_block(thinking)),
                    )

    def _get_tool_title(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Generate a human-readable title for a tool call."""
        if tool_name == "Read":
            path = tool_input.get("file_path", tool_input.get("path", ""))
            return f"Read {path}"
        elif tool_name in ["Write", "Edit"]:
            path = tool_input.get("file_path", tool_input.get("path", ""))
            return f"{tool_name} {path}"
        elif tool_name == "Bash":
            cmd = tool_input.get("command", "")
            return f"Run: {cmd[:50]}..." if len(cmd) > 50 else f"Run: {cmd}"
        elif tool_name == "Glob":
            pattern = tool_input.get("pattern", "")
            return f"Find files: {pattern}"
        elif tool_name == "Grep":
            pattern = tool_input.get("pattern", "")
            return f"Search: {pattern}"
        else:
            return tool_name

    def _create_permission_handler(self, session_id: str):
        """Create a permission handler for bidirectional permission requests."""

        async def _apply_tool_input_transform(
            tool_name: str, tool_input: dict[str, Any],
        ) -> dict[str, Any] | None:
            """套用 tool input transform（如有設定）。"""
            if self._tool_input_transform is None:
                return None
            try:
                return await self._tool_input_transform(tool_name, tool_input)
            except Exception as e:
                logger.warning(f"tool_input_transform 失敗: {e}")
                return None

        async def can_use_tool(
            tool_name: str,
            tool_input: dict[str, Any],
            context: ToolPermissionContext,
        ) -> PermissionResultAllow | PermissionResultDeny:
            logger.info(f"🔧 Permission requested for tool: {tool_name}")

            if self._conn is None:
                logger.warning("No ACP connection for permission request")
                return PermissionResultDeny(message="No ACP connection")

            session = self._sessions.get(session_id)
            if session is None:
                return PermissionResultDeny(message="Session not found")

            # For certain modes, auto-allow
            if session.permission_mode == "bypassPermissions":
                updated = await _apply_tool_input_transform(tool_name, tool_input)
                return PermissionResultAllow(updated_input=updated)

            if session.permission_mode == "acceptEdits" and tool_name in [
                "Write",
                "Edit",
                "MultiEdit",
            ]:
                return PermissionResultAllow()

            # Request permission from ACP client
            tool_use_id = str(uuid4())

            response = await self._conn.request_permission(
                options=[
                    PermissionOption(
                        kind="allow_always",
                        name="Always Allow",
                        option_id="allow_always",
                    ),
                    PermissionOption(
                        kind="allow_once",
                        name="Allow",
                        option_id="allow",
                    ),
                    PermissionOption(
                        kind="reject_once",
                        name="Reject",
                        option_id="reject",
                    ),
                ],
                session_id=session_id,
                tool_call={
                    "tool_call_id": tool_use_id,
                    "title": self._get_tool_title(tool_name, tool_input),
                    "raw_input": tool_input,
                },
            )

            # Handle RequestPermissionResponse object
            outcome = response.outcome
            if outcome and outcome.outcome == "selected":
                option_id = outcome.option_id
                if option_id in ["allow", "allow_always"]:
                    updated = await _apply_tool_input_transform(tool_name, tool_input)
                    return PermissionResultAllow(updated_input=updated)

            return PermissionResultDeny(message="User denied permission")

        return can_use_tool

    async def _get_server_info(
        self,
        cwd: str,
        mcp_servers: dict[str, Any],
        system_prompt: str | dict | None,
    ) -> dict[str, Any] | None:
        """Get server info (commands, models) by creating a temporary client."""
        try:
            extra_args = {}
            if mcp_servers:
                extra_args["strict-mcp-config"] = None

            options = ClaudeAgentOptions(
                cwd=cwd,
                mcp_servers=mcp_servers if mcp_servers else {},
                system_prompt=system_prompt,
                extra_args=extra_args,
            )

            client = ClaudeSDKClient(options)
            await client.connect()

            try:
                server_info = await client.get_server_info()
                logger.info(f"Got server info: {len(server_info.get('commands', []))} commands, {len(server_info.get('models', []))} models")
                return server_info
            finally:
                await client.disconnect()

        except Exception as e:
            logger.warning(f"Failed to get server info: {e}")
            return None

    def _build_models_state(self, server_info: dict[str, Any] | None) -> SessionModelState | None:
        """Build SessionModelState from server_info."""
        if server_info is None or "models" not in server_info:
            return None

        models_data = server_info.get("models", [])
        if not models_data:
            return None

        available_models = []
        current_model_id = "default"

        for model in models_data:
            model_id = model.get("value", "")
            available_models.append(
                ModelInfo(
                    model_id=model_id,
                    name=model.get("displayName", model_id),
                    description=model.get("description"),
                )
            )
            # First model is usually the default
            if not current_model_id or model_id == "default":
                current_model_id = model_id

        if not available_models:
            return None

        return SessionModelState(
            available_models=available_models,
            current_model_id=current_model_id,
        )

    async def _send_available_commands(
        self,
        session_id: str,
        server_info: dict[str, Any],
    ) -> None:
        """Send AvailableCommandsUpdate to the ACP client."""
        if self._conn is None:
            return

        commands_data = server_info.get("commands", [])
        if not commands_data:
            return

        # Filter out some commands that don't work well in ACP context
        unsupported_commands = {
            "cost",
            "keybindings-help",
            "login",
            "logout",
            "output-style:new",
            "release-notes",
            "todos",
        }

        available_commands: list[AvailableCommand] = []
        for cmd in commands_data:
            name = cmd.get("name", "")
            if name in unsupported_commands:
                continue

            # Handle MCP commands (name ends with " (MCP)")
            if name.endswith(" (MCP)"):
                name = f"mcp:{name.replace(' (MCP)', '')}"

            # Build input specification if argumentHint is present
            cmd_input = None
            argument_hint = cmd.get("argumentHint", "")
            if argument_hint:
                cmd_input = AvailableCommandInput(root={"hint": argument_hint})

            available_commands.append(
                AvailableCommand(
                    name=name,
                    description=cmd.get("description", ""),
                    input=cmd_input,
                )
            )

        if available_commands:
            try:
                await self._conn.session_update(
                    session_id,
                    update_available_commands(available_commands),
                )
                logger.info(f"Sent {len(available_commands)} available commands for session {session_id}")
            except Exception as e:
                logger.warning(f"Failed to send available commands: {e}")

    # --- Additional ACP Methods ---

    async def list_sessions(
        self,
        cursor: str | None = None,
        cwd: str | None = None,
        **kwargs: Any,
    ):
        """List available sessions."""
        from acp.schema import ListSessionsResponse, SessionInfo

        sessions = []
        for session_id, session in self._sessions.items():
            if cwd is None or session.cwd == cwd:
                sessions.append(
                    SessionInfo(
                        sessionId=session_id,
                        cwd=session.cwd,
                    )
                )

        return ListSessionsResponse(sessions=sessions)

    async def load_session(
        self,
        cwd: str,
        mcp_servers: list,
        session_id: str,
        **kwargs: Any,
    ):
        """Load an existing session."""
        from acp.schema import LoadSessionResponse

        if session_id not in self._sessions:
            return None

        session = self._sessions[session_id]
        session.cwd = cwd

        return LoadSessionResponse()

    async def fork_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list | None = None,
        **kwargs: Any,
    ):
        """Fork an existing session."""
        from acp.schema import ForkSessionResponse

        if session_id not in self._sessions:
            raise ValueError(f"Session not found: {session_id}")

        new_session_id = str(uuid4())
        old_session = self._sessions[session_id]

        self._sessions[new_session_id] = Session(
            session_id=new_session_id,
            cwd=cwd,
            permission_mode=old_session.permission_mode,
        )

        logger.info(f"Forked session {session_id} to {new_session_id}")

        return ForkSessionResponse(session_id=new_session_id)

    async def resume_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list | None = None,
        **kwargs: Any,
    ):
        """Resume an existing session."""
        from acp.schema import ResumeSessionResponse

        if session_id not in self._sessions:
            raise ValueError(f"Session not found: {session_id}")

        session = self._sessions[session_id]
        session.cwd = cwd
        session.cancelled = False

        logger.info(f"Resumed session {session_id}")

        return ResumeSessionResponse()

    async def authenticate(self, method_id: str, **kwargs: Any):
        """Handle authentication requests."""
        from acp.schema import AuthenticateResponse

        logger.info(f"Authentication requested: {method_id}")

        # For Claude login, the user needs to run `claude /login` in terminal
        # The AuthenticateResponse is empty per ACP spec - auth status is handled differently
        return AuthenticateResponse()

    async def set_session_model(
        self,
        model_id: str,
        session_id: str,
        **kwargs: Any,
    ):
        """Set the model for a session."""
        from acp.schema import SetSessionModelResponse

        session = self._sessions.get(session_id)
        if session:
            logger.info(f"Setting model for session {session_id}: {model_id}")
            session.model = model_id
            # Close existing client so next prompt creates a fresh one with the new model
            if session.client and session.client_started:
                try:
                    await session.client.__aexit__(None, None, None)
                except Exception as e:
                    logger.warning(f"Error closing client: {e}")
                session.client = None
                session.client_started = False
        else:
            logger.warning(f"Session not found for model change: {session_id}")

        return SetSessionModelResponse()

    # --- Lifecycle Methods ---

    async def close_session(self, session_id: str) -> None:
        """Close a specific session and clean up its client resources."""
        session = self._sessions.pop(session_id, None)
        if session is None:
            return

        if session.client and session.client_started:
            try:
                await session.client.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing client for session {session_id}: {e}")
            session.client = None
            session.client_started = False

        logger.info(f"Session {session_id} closed")

    async def close(self) -> None:
        """Close all sessions and clean up resources."""
        session_ids = list(self._sessions.keys())
        for session_id in session_ids:
            await self.close_session(session_id)
        logger.info("All sessions closed")

    async def __aenter__(self) -> "ClaudeAcpAgent":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    # --- Extension Methods ---

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Handle extension method calls."""
        logger.info(f"Extension method: {method}")
        return {"status": "ok"}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        """Handle extension notifications."""
        logger.info(f"Extension notification: {method}")
