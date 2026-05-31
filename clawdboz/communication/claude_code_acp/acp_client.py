"""
ACP Client - Connect to any ACP-compatible agent.

This module provides a client that can connect to any ACP agent
(like claude-code-acp, or Zed's TypeScript version) via subprocess.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Coroutine

from acp import spawn_agent_process
from acp.client.connection import ClientSideConnection
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    AllowedOutcome,
    EnvVariable,
    Implementation,
    McpServerStdio,
    PermissionOption,
    RequestPermissionResponse,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
)

logger = logging.getLogger(__name__)

__all__ = ["AcpClient", "AcpClientEvents"]


@dataclass
class TerminalProcess:
    """Represents an active terminal process."""

    process: asyncio.subprocess.Process
    command: str
    cwd: str
    output_buffer: list[str]
    exit_code: int | None = None


@dataclass
class AcpClientEvents:
    """Event handlers for ACP client."""

    on_text: Callable[[str], Coroutine[Any, Any, None]] | None = None
    on_thinking: Callable[[str], Coroutine[Any, Any, None]] | None = None
    on_tool_start: Callable[[str, str, dict], Coroutine[Any, Any, None]] | None = None
    on_tool_end: Callable[[str, str, Any], Coroutine[Any, Any, None]] | None = None
    on_permission: Callable[[str, dict, list], Coroutine[Any, Any, str]] | None = None
    on_error: Callable[[Exception], Coroutine[Any, Any, None]] | None = None
    on_complete: Callable[[], Coroutine[Any, Any, None]] | None = None
    # File operation handlers (optional - if not set, operations proceed automatically)
    on_file_read: Callable[[str], Coroutine[Any, Any, str | None]] | None = None
    on_file_write: Callable[[str, str], Coroutine[Any, Any, bool]] | None = None
    # Terminal operation handlers (optional)
    on_terminal_create: Callable[[str, str], Coroutine[Any, Any, bool]] | None = None
    on_terminal_output: Callable[[str, str], Coroutine[Any, Any, None]] | None = None


class AcpClient:
    """
    ACP Client that connects to any ACP-compatible agent.

    This client spawns an ACP agent as a subprocess and communicates
    via the Agent Client Protocol (JSON-RPC over stdio).

    Example:
        ```python
        # Connect to claude-code-acp
        client = AcpClient(command="claude-code-acp")

        # Or connect to the TypeScript version
        client = AcpClient(command="npx", args=["@anthropic/claude-code-acp"])

        @client.on_text
        async def handle_text(text):
            print(text, end="")

        async with client:
            await client.prompt("Hello!")
        ```
    """

    def __init__(
        self,
        command: str = "claude-code-acp",
        args: list[str] | None = None,
        cwd: str = ".",
        env: dict[str, str] | None = None,
        mcp_servers: list[dict] | None = None,
    ):
        """
        Initialize the ACP client.

        Args:
            command: The ACP agent command to run.
            args: Additional arguments for the command.
            cwd: Working directory for the agent.
            env: Additional environment variables.
            mcp_servers: List of MCP server configurations.
                Each dict should have: name, command, args (list), env (optional dict).
        """
        self.command = command
        self.args = args or []
        self.cwd = cwd
        self.env = env
        self.mcp_servers = mcp_servers or []
        self.events = AcpClientEvents()

        self._process: asyncio.subprocess.Process | None = None
        self._connection: ClientSideConnection | None = None
        self._session_id: str | None = None
        self._text_buffer = ""
        self._initialized = False
        # Model to set after session is created
        self._pending_model: str | None = None
        # Terminal management
        self._terminals: dict[str, TerminalProcess] = {}
        self._terminal_counter = 0

    # --- Event decorators ---

    def on_text(self, func: Callable[[str], Coroutine[Any, Any, None]]):
        """Register handler for text responses."""
        self.events.on_text = func
        return func

    def on_thinking(self, func: Callable[[str], Coroutine[Any, Any, None]]):
        """Register handler for thinking blocks."""
        self.events.on_thinking = func
        return func

    def on_tool_start(self, func: Callable[[str, str, dict], Coroutine[Any, Any, None]]):
        """Register handler for tool start events."""
        self.events.on_tool_start = func
        return func

    def on_tool_end(self, func: Callable[[str, str, Any], Coroutine[Any, Any, None]]):
        """Register handler for tool end events."""
        self.events.on_tool_end = func
        return func

    def on_permission(self, func: Callable[[str, dict, list], Coroutine[Any, Any, str]]):
        """
        Register handler for permission requests.

        The handler receives (name, input, options) and should return
        the option_id to select (e.g., "allow", "reject", "allow_always").
        """
        self.events.on_permission = func
        return func

    def on_error(self, func: Callable[[Exception], Coroutine[Any, Any, None]]):
        """Register handler for errors."""
        self.events.on_error = func
        return func

    def on_complete(self, func: Callable[[], Coroutine[Any, Any, None]]):
        """Register handler for completion."""
        self.events.on_complete = func
        return func

    def on_file_read(self, func: Callable[[str], Coroutine[Any, Any, str | None]]):
        """
        Register handler for file read operations.

        The handler receives (path) and can return:
        - str: Override the file content with this value
        - None: Proceed with normal file reading

        This allows intercepting file reads for security or custom handling.
        """
        self.events.on_file_read = func
        return func

    def on_file_write(self, func: Callable[[str, str], Coroutine[Any, Any, bool]]):
        """
        Register handler for file write operations.

        The handler receives (path, content) and should return:
        - True: Allow the write to proceed
        - False: Block the write

        This allows intercepting file writes for security or confirmation prompts.
        """
        self.events.on_file_write = func
        return func

    def on_terminal_create(self, func: Callable[[str, str], Coroutine[Any, Any, bool]]):
        """
        Register handler for terminal creation requests.

        The handler receives (command, cwd) and should return:
        - True: Allow the terminal to be created
        - False: Block the terminal creation

        This allows intercepting shell command execution for security.
        """
        self.events.on_terminal_create = func
        return func

    def on_terminal_output(self, func: Callable[[str, str], Coroutine[Any, Any, None]]):
        """
        Register handler for terminal output.

        The handler receives (terminal_id, output) when new output is available.
        This allows displaying or logging terminal output in real-time.
        """
        self.events.on_terminal_output = func
        return func

    # --- Connection management ---

    async def connect(self) -> None:
        """Connect to the ACP agent."""
        if self._process is not None:
            return

        # Spawn the agent process
        self._process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=self.env,
        )

        if self._process.stdin is None or self._process.stdout is None:
            raise RuntimeError("Failed to create subprocess pipes")

        # Create ACP connection
        # Note: ClientSideConnection expects (writer, reader) - stdin is writer, stdout is reader
        self._connection = ClientSideConnection(
            to_client=self._create_client_handler(),
            input_stream=self._process.stdin,
            output_stream=self._process.stdout,
        )

        # Initialize the connection
        init_response = await self._connection.initialize(
            protocol_version=1,
            client_info=Implementation(
                name="claude-code-acp-client",
                version="0.2.0",
            ),
        )
        logger.info(f"Connected to agent: {init_response.agent_info}")
        self._initialized = True

    async def disconnect(self) -> None:
        """Disconnect from the ACP agent."""
        # Clean up all terminals
        for terminal_id, terminal in list(self._terminals.items()):
            try:
                terminal.process.kill()
                await terminal.process.wait()
            except Exception:
                pass
        self._terminals.clear()

        # Close connection with timeout to avoid hanging
        if self._connection:
            try:
                await asyncio.wait_for(self._connection.close(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Connection close timed out")
            except Exception as e:
                logger.debug(f"Connection close error (ignored): {e}")
            self._connection = None

        # Terminate subprocess with timeout
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                logger.warning("Process terminate timed out, killing")
                self._process.kill()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning("Process kill timed out")
            # Close stdin pipe to prevent 'Event loop is closed' errors during GC
            # Note: stdout/stderr are StreamReader objects which don't have close()
            if self._process.stdin:
                self._process.stdin.close()
            self._process = None

        self._initialized = False
        self._session_id = None

    async def __aenter__(self) -> "AcpClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.disconnect()

    # --- Session management ---

    async def new_session(self) -> str:
        """Create a new session."""
        if not self._connection:
            raise RuntimeError("Not connected")

        # Convert MCP server configs to ACP schema
        mcp_servers_acp = []
        for srv in self.mcp_servers:
            env_vars = []
            if "env" in srv and srv["env"]:
                for k, v in srv["env"].items():
                    env_vars.append(EnvVariable(name=k, value=v))
            mcp_servers_acp.append(
                McpServerStdio(
                    name=srv.get("name", "mcp"),
                    command=srv.get("command", ""),
                    args=srv.get("args", []),
                    env=env_vars,
                )
            )

        response = await self._connection.new_session(
            cwd=self.cwd,
            mcp_servers=mcp_servers_acp,
        )
        self._session_id = response.session_id

        # Apply pending model if one was set before session creation
        if self._pending_model:
            try:
                await self._connection.set_session_model(
                    model_id=self._pending_model,
                    session_id=self._session_id,
                )
                logger.info(f"Applied pending model '{self._pending_model}' to session {self._session_id}")
            except Exception as e:
                logger.warning(f"Failed to apply pending model: {e}")
            finally:
                self._pending_model = None

        return self._session_id

    async def prompt(self, text: str) -> str:
        """
        Send a prompt and receive the response.

        Events will be dispatched to registered handlers as they arrive.

        Args:
            text: The prompt text to send.

        Returns:
            The full text response.
        """
        if not self._connection:
            raise RuntimeError("Not connected")

        if not self._session_id:
            await self.new_session()

        self._text_buffer = ""

        try:
            response = await self._connection.prompt(
                prompt=[TextContentBlock(type="text", text=text)],
                session_id=self._session_id,
            )

            if self.events.on_complete:
                await self.events.on_complete()

            return self._text_buffer

        except Exception as e:
            if self.events.on_error:
                await self.events.on_error(e)
            raise

    async def cancel(self) -> None:
        """Cancel the current operation."""
        if self._connection and self._session_id:
            await self._connection.cancel(session_id=self._session_id)

    async def set_mode(self, mode: str) -> None:
        """Set the permission mode."""
        if not self._connection or not self._session_id:
            raise RuntimeError("No active session")

        await self._connection.set_session_mode(
            mode_id=mode,
            session_id=self._session_id,
        )

    async def set_model(self, model: str) -> None:
        """Set the model for the current session.

        If no session exists yet, the model will be stored and applied
        when the session is created.
        """
        if not self._connection or not self._session_id:
            # Store for later - will be applied when session is created
            self._pending_model = model
            logger.info(f"Model '{model}' stored, will be applied when session is created")
            return

        await self._connection.set_session_model(
            model_id=model,
            session_id=self._session_id,
        )
        logger.info(f"Model set to '{model}'")

    # --- Internal handlers ---

    def _create_client_handler(self):
        """Create the client handler for receiving agent messages."""
        client = self

        class ClientHandler:
            """Handles incoming messages from the agent."""

            async def session_update(self, session_id: str, update: Any) -> None:
                """Handle session updates from the agent."""
                update_type = type(update).__name__

                if isinstance(update, AgentMessageChunk):
                    content = getattr(update, "content", None)
                    if content and hasattr(content, "text"):
                        text = content.text
                        if text and text not in client._text_buffer:
                            client._text_buffer += text
                            if client.events.on_text:
                                await client.events.on_text(text)

                elif isinstance(update, AgentThoughtChunk):
                    content = getattr(update, "content", None)
                    if content and hasattr(content, "text"):
                        if client.events.on_thinking:
                            await client.events.on_thinking(content.text)

                elif isinstance(update, ToolCallStart):
                    if client.events.on_tool_start:
                        await client.events.on_tool_start(
                            update.tool_call_id,
                            update.title or "",
                            update.raw_input or {},
                        )

                elif isinstance(update, ToolCallProgress):
                    if client.events.on_tool_end:
                        await client.events.on_tool_end(
                            update.tool_call_id,
                            update.status or "",
                            update.raw_output,
                        )

            async def request_permission(
                self,
                options: list[PermissionOption],
                session_id: str,
                tool_call: ToolCallUpdate,
                **kwargs: Any,
            ) -> RequestPermissionResponse:
                """Handle permission requests from the agent."""
                name = tool_call.title or "Unknown"
                raw_input = tool_call.raw_input or {}
                option_list = [{"id": o.option_id, "name": o.name} for o in options]

                # Default to allow
                selected_id = "allow"

                if client.events.on_permission:
                    selected_id = await client.events.on_permission(
                        name, raw_input, option_list
                    )

                return RequestPermissionResponse(
                    outcome=AllowedOutcome(outcome="selected", option_id=selected_id)
                )

            async def write_text_file(
                self,
                path: str,
                content: str,
                **kwargs,
            ) -> None:
                """
                Handle write file requests from the agent.

                The agent requests the client to write a file to disk.
                This enables the agent to create/modify files in the user's filesystem.

                Args:
                    path: The file path to write to.
                    content: The content to write.
                """
                # Check if handler wants to intercept/block the write
                if client.events.on_file_write:
                    allowed = await client.events.on_file_write(path, content)
                    if not allowed:
                        logger.info(f"File write blocked by handler: {path}")
                        return

                try:
                    file_path = Path(path)
                    # Create parent directories if they don't exist
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    # Write the file
                    file_path.write_text(content, encoding="utf-8")
                    logger.debug(f"Wrote file: {path}")
                except Exception as e:
                    logger.error(f"Failed to write file {path}: {e}")
                    raise

            async def read_text_file(
                self,
                path: str,
                **kwargs,
            ) -> dict:
                """
                Handle read file requests from the agent.

                The agent requests the client to read a file from disk.
                This enables the agent to access files in the user's filesystem.

                Args:
                    path: The file path to read.

                Returns:
                    A dict with 'content' key containing the file content.
                """
                # Check if handler wants to override the content
                if client.events.on_file_read:
                    override = await client.events.on_file_read(path)
                    if override is not None:
                        logger.debug(f"File read overridden by handler: {path}")
                        return {"content": override}

                try:
                    file_path = Path(path)
                    if not file_path.exists():
                        logger.warning(f"File not found: {path}")
                        return {"content": "", "error": f"File not found: {path}"}
                    content = file_path.read_text(encoding="utf-8")
                    logger.debug(f"Read file: {path} ({len(content)} chars)")
                    return {"content": content}
                except Exception as e:
                    logger.error(f"Failed to read file {path}: {e}")
                    return {"content": "", "error": str(e)}

            async def create_terminal(
                self,
                command: str = "",
                args: list[str] | None = None,
                cwd: str | None = None,
                env: dict[str, str] | None = None,
                **kwargs,
            ) -> dict:
                """
                Create a terminal and execute a command.

                The agent requests the client to run a shell command.
                This enables command execution in the user's environment.

                Args:
                    command: The command to execute.
                    args: Command arguments.
                    cwd: Working directory (defaults to client cwd).
                    env: Additional environment variables.

                Returns:
                    A dict with 'terminal_id' for tracking the process.
                """
                work_dir = cwd or client.cwd
                full_command = command
                if args:
                    full_command = f"{command} {' '.join(args)}"

                # Check if handler wants to block the terminal creation
                if client.events.on_terminal_create:
                    allowed = await client.events.on_terminal_create(full_command, work_dir)
                    if not allowed:
                        logger.info(f"Terminal creation blocked by handler: {full_command}")
                        return {"terminal_id": "", "error": "Terminal creation blocked"}

                try:
                    # Create the subprocess
                    process = await asyncio.create_subprocess_shell(
                        full_command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                        cwd=work_dir,
                        env={**dict(env or {})} if env else None,
                    )

                    # Generate terminal ID
                    client._terminal_counter += 1
                    terminal_id = f"terminal-{client._terminal_counter}"

                    # Store the terminal
                    client._terminals[terminal_id] = TerminalProcess(
                        process=process,
                        command=full_command,
                        cwd=work_dir,
                        output_buffer=[],
                    )

                    logger.debug(f"Created terminal {terminal_id}: {full_command}")
                    return {"terminal_id": terminal_id}

                except Exception as e:
                    logger.error(f"Failed to create terminal: {e}")
                    return {"terminal_id": "", "error": str(e)}

            async def terminal_output(
                self,
                terminal_id: str = "",
                **kwargs,
            ) -> dict:
                """
                Get output from a terminal.

                Args:
                    terminal_id: The terminal to get output from.

                Returns:
                    A dict with 'output' containing available output.
                """
                terminal = client._terminals.get(terminal_id)
                if not terminal:
                    return {"output": "", "error": f"Terminal not found: {terminal_id}"}

                try:
                    # Try to read available output (non-blocking)
                    if terminal.process.stdout:
                        try:
                            # Read with a short timeout
                            output = await asyncio.wait_for(
                                terminal.process.stdout.read(4096),
                                timeout=0.1,
                            )
                            if output:
                                decoded = output.decode("utf-8", errors="replace")
                                terminal.output_buffer.append(decoded)

                                # Notify handler if registered
                                if client.events.on_terminal_output:
                                    await client.events.on_terminal_output(terminal_id, decoded)

                                return {"output": decoded}
                        except asyncio.TimeoutError:
                            pass

                    # Return buffered output if no new output
                    if terminal.output_buffer:
                        return {"output": "".join(terminal.output_buffer)}
                    return {"output": ""}

                except Exception as e:
                    logger.error(f"Failed to get terminal output: {e}")
                    return {"output": "", "error": str(e)}

            async def release_terminal(
                self,
                terminal_id: str = "",
                **kwargs,
            ) -> None:
                """
                Release a terminal without killing it.

                The terminal continues running but we stop tracking it.

                Args:
                    terminal_id: The terminal to release.
                """
                if terminal_id in client._terminals:
                    logger.debug(f"Released terminal: {terminal_id}")
                    del client._terminals[terminal_id]

            async def wait_for_terminal_exit(
                self,
                terminal_id: str = "",
                **kwargs,
            ) -> dict:
                """
                Wait for a terminal to exit and return its exit code.

                Args:
                    terminal_id: The terminal to wait for.

                Returns:
                    A dict with 'exit_code'.
                """
                terminal = client._terminals.get(terminal_id)
                if not terminal:
                    return {"exit_code": -1, "error": f"Terminal not found: {terminal_id}"}

                try:
                    # Read remaining output while waiting
                    if terminal.process.stdout:
                        remaining = await terminal.process.stdout.read()
                        if remaining:
                            decoded = remaining.decode("utf-8", errors="replace")
                            terminal.output_buffer.append(decoded)
                            if client.events.on_terminal_output:
                                await client.events.on_terminal_output(terminal_id, decoded)

                    # Wait for process to exit
                    exit_code = await terminal.process.wait()
                    terminal.exit_code = exit_code
                    logger.debug(f"Terminal {terminal_id} exited with code {exit_code}")
                    return {"exit_code": exit_code}

                except Exception as e:
                    logger.error(f"Failed to wait for terminal exit: {e}")
                    return {"exit_code": -1, "error": str(e)}

            async def kill_terminal(
                self,
                terminal_id: str = "",
                **kwargs,
            ) -> None:
                """
                Kill a terminal process.

                Args:
                    terminal_id: The terminal to kill.
                """
                terminal = client._terminals.get(terminal_id)
                if not terminal:
                    return

                try:
                    terminal.process.kill()
                    await terminal.process.wait()
                    logger.debug(f"Killed terminal: {terminal_id}")
                except Exception as e:
                    logger.error(f"Failed to kill terminal: {e}")

                # Remove from tracking
                if terminal_id in client._terminals:
                    del client._terminals[terminal_id]

            async def ext_method(self, method: str, params: dict) -> dict:
                """Handle extension methods."""
                return {}

            async def ext_notification(self, method: str, params: dict) -> None:
                """Handle extension notifications."""
                pass

            def on_connect(self, conn: Any) -> None:
                """Called when connected."""
                pass

        return ClientHandler()
