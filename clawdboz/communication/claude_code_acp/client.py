"""
Event-driven Claude client wrapper.

Provides a simple, decorator-based API for interacting with Claude.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from .agent import ClaudeAcpAgent


@dataclass
class ClaudeEvents:
    """Event handlers for Claude responses."""

    on_text: Callable[[str], Coroutine[Any, Any, None]] | None = None
    on_thinking: Callable[[str], Coroutine[Any, Any, None]] | None = None
    on_tool_start: Callable[[str, str, dict], Coroutine[Any, Any, None]] | None = None
    on_tool_end: Callable[[str, str, Any], Coroutine[Any, Any, None]] | None = None
    on_permission: Callable[[str, dict], Coroutine[Any, Any, bool]] | None = None
    on_error: Callable[[Exception], Coroutine[Any, Any, None]] | None = None
    on_complete: Callable[[], Coroutine[Any, Any, None]] | None = None
    on_result: Callable[[dict], Coroutine[Any, Any, None]] | None = None
    on_tool_input_transform: Callable[[str, dict], Coroutine[Any, Any, dict | None]] | None = None


class ClaudeClient:
    """
    Event-driven Claude client using ACP.

    Example:
        ```python
        client = ClaudeClient(cwd="/path/to/project")

        @client.on_text
        async def handle_text(text):
            print(text, end="", flush=True)

        @client.on_tool_start
        async def handle_tool(tool_id, name, input):
            print(f"Running: {name}")

        @client.on_permission
        async def handle_permission(name, input):
            return True  # or prompt user

        response = await client.query("What files are in this directory?")
        ```
    """

    def __init__(self, cwd: str = ".", mcp_servers: list | None = None, system_prompt: str | dict | None = None):
        """
        Initialize the Claude client.

        Args:
            cwd: Working directory for Claude operations.
            mcp_servers: List of MCP server configurations.
            system_prompt: Custom system prompt for Claude. Can be:
                - str: Plain text system prompt
                - dict: {"type": "preset", "preset": "claude_code", "append": "..."}
        """
        self.cwd = cwd
        self.mcp_servers = mcp_servers or []
        self.system_prompt = system_prompt
        self.agent = ClaudeAcpAgent()
        self.session_id: str | None = None
        self.events = ClaudeEvents()
        self._text_buffer = ""
        self._seen_text = set()  # Track seen text to avoid duplicates
        # Token usage from the last query
        self.input_tokens: int | None = None
        self.output_tokens: int | None = None
        self.total_cost_usd: float | None = None

    # --- Decorator-based event registration ---

    def on_text(self, func: Callable[[str], Coroutine[Any, Any, None]]):
        """
        Register handler for text responses.

        The handler receives streaming text chunks as they arrive.

        Example:
            @client.on_text
            async def handle_text(text: str):
                print(text, end="", flush=True)
        """
        self.events.on_text = func
        return func

    def on_thinking(self, func: Callable[[str], Coroutine[Any, Any, None]]):
        """
        Register handler for thinking/reasoning blocks.

        Example:
            @client.on_thinking
            async def handle_thinking(text: str):
                print(f"[Thinking: {text}]")
        """
        self.events.on_thinking = func
        return func

    def on_tool_start(
        self, func: Callable[[str, str, dict], Coroutine[Any, Any, None]]
    ):
        """
        Register handler for tool call start events.

        Args to handler:
            tool_id: Unique identifier for the tool call
            name: Human-readable tool name/title
            input: Tool input parameters

        Example:
            @client.on_tool_start
            async def handle_tool_start(tool_id: str, name: str, input: dict):
                print(f"🔧 Starting: {name}")
        """
        self.events.on_tool_start = func
        return func

    def on_tool_end(self, func: Callable[[str, str, Any], Coroutine[Any, Any, None]]):
        """
        Register handler for tool completion events.

        Args to handler:
            tool_id: Unique identifier for the tool call
            status: "completed" or "failed"
            output: Tool output/result

        Example:
            @client.on_tool_end
            async def handle_tool_end(tool_id: str, status: str, output: Any):
                icon = "✅" if status == "completed" else "❌"
                print(f" {icon}")
        """
        self.events.on_tool_end = func
        return func

    def on_permission(
        self, func: Callable[[str, dict], Coroutine[Any, Any, bool]]
    ):
        """
        Register handler for permission requests.

        The handler should return True to allow, False to deny.

        Example:
            @client.on_permission
            async def handle_permission(name: str, input: dict) -> bool:
                response = input("Allow {name}? [y/N]: ")
                return response.lower() == "y"
        """
        self.events.on_permission = func
        return func

    def on_error(self, func: Callable[[Exception], Coroutine[Any, Any, None]]):
        """
        Register handler for errors.

        Example:
            @client.on_error
            async def handle_error(e: Exception):
                print(f"Error: {e}")
        """
        self.events.on_error = func
        return func

    def on_complete(self, func: Callable[[], Coroutine[Any, Any, None]]):
        """
        Register handler for query completion.

        Example:
            @client.on_complete
            async def handle_complete():
                print("\\n--- Done ---")
        """
        self.events.on_complete = func
        return func

    def on_result(self, func: Callable[[dict], Coroutine[Any, Any, None]]):
        """
        Register handler for result/usage info.

        The handler receives a dict with keys like:
        - input_tokens, output_tokens (from usage)
        - total_cost_usd
        - duration_ms, duration_api_ms
        - num_turns, is_error, result

        Example:
            @client.on_result
            async def handle_result(info: dict):
                print(f"Tokens: {info.get('input_tokens')}/{info.get('output_tokens')}")
        """
        self.events.on_result = func
        return func

    def on_tool_input_transform(
        self,
        func: Callable[[str, dict], Coroutine[Any, Any, dict | None]],
    ):
        """
        Register handler to transform tool input before execution.

        Called after permission is granted, before the tool runs.
        Use this to inject, override, or sanitize tool parameters
        at the framework level (independent of LLM behavior).

        The handler receives (tool_name, tool_input) and should return:
        - dict: The modified input to use (replaces original)
        - None: Keep the original input unchanged

        Example:
            @client.on_tool_input_transform
            async def inject_user(name: str, input: dict) -> dict | None:
                if name.startswith("mcp__my-server__"):
                    return {**input, "user_id": current_user_id}
                return None
        """
        self.events.on_tool_input_transform = func
        return func

    # --- Lifecycle ---

    async def close(self) -> None:
        """Close the client and clean up all resources."""
        await self.agent.close()

    async def __aenter__(self) -> "ClaudeClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    # --- Main API ---

    async def start_session(self) -> str:
        """
        Start a new Claude session.

        Returns:
            The session ID.
        """
        session = await self.agent.new_session(cwd=self.cwd, mcp_servers=self.mcp_servers, system_prompt=self.system_prompt)
        self.session_id = session.session_id
        return self.session_id

    async def query(self, prompt: str) -> str:
        """
        Send a query and receive events via registered handlers.

        Args:
            prompt: The message to send to Claude.

        Returns:
            The full text response as a string.

        Example:
            response = await client.query("Explain this code")
            print(f"Full response: {response}")
        """
        if not self.session_id:
            await self.start_session()

        self._text_buffer = ""
        self._seen_text = set()
        self.input_tokens = None
        self.output_tokens = None
        self.total_cost_usd = None

        # Wire up the event handler
        self.agent._conn = self._create_event_handler()

        # Wire up tool input transform（不走 ACP protocol，直接傳遞 Python 參考）
        self.agent._tool_input_transform = self.events.on_tool_input_transform

        # Wire up result callback for token usage
        async def _handle_result(result_msg):
            usage = result_msg.usage or {}
            # 計算完整的 input tokens（含快取）
            self.input_tokens = (
                usage.get("input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0)
                + usage.get("cache_read_input_tokens", 0)
            )
            self.output_tokens = usage.get("output_tokens")
            self.total_cost_usd = result_msg.total_cost_usd
            if self.events.on_result:
                info = {
                    "input_tokens": self.input_tokens,
                    "output_tokens": self.output_tokens,
                    "total_cost_usd": self.total_cost_usd,
                    "duration_ms": result_msg.duration_ms,
                    "duration_api_ms": result_msg.duration_api_ms,
                    "num_turns": result_msg.num_turns,
                    "is_error": result_msg.is_error,
                    "result": result_msg.result,
                    "usage": usage,
                }
                await self.events.on_result(info)

        self.agent._on_result = _handle_result

        try:
            await self.agent.prompt(
                prompt=[{"type": "text", "text": prompt}],
                session_id=self.session_id,
            )

            if self.events.on_complete:
                await self.events.on_complete()

        except Exception as e:
            if self.events.on_error:
                await self.events.on_error(e)
            raise

        return self._text_buffer

    async def set_mode(self, mode: str) -> None:
        """
        Set the permission mode for the session.

        Args:
            mode: One of "default", "acceptEdits", "plan", "bypassPermissions"
        """
        if not self.session_id:
            await self.start_session()

        await self.agent.set_session_mode(mode_id=mode, session_id=self.session_id)

    async def set_model(self, model: str) -> None:
        """Set the model for the current session."""
        if not self.session_id:
            await self.start_session()
        await self.agent.set_session_model(
            model_id=model,
            session_id=self.session_id,
        )

    def _create_event_handler(self):
        """Create the internal event handler that bridges to user callbacks."""
        client = self

        class EventHandler:
            async def session_update(self, session_id: str, update: Any) -> None:
                update_type = type(update).__name__
                import logging
                logging.getLogger(__name__).debug(f"session_update: {update_type}")

                if "AgentMessageChunk" in update_type:
                    content = getattr(update, "content", None)
                    if content and hasattr(content, "text"):
                        text = content.text
                        if not text:
                            return

                        # Smart deduplication for streaming:
                        # - If text == buffer, exact duplicate, skip
                        # - If text extends buffer (cumulative), emit only new part
                        # - Otherwise, this is a new delta chunk, append and emit
                        current_len = len(client._text_buffer)

                        if current_len == 0:
                            # First chunk
                            client._text_buffer = text
                            if client.events.on_text:
                                await client.events.on_text(text)
                        elif text == client._text_buffer:
                            # Exact duplicate, skip
                            pass
                        elif text.startswith(client._text_buffer):
                            # Cumulative update - text extends buffer, emit only new part
                            new_part = text[current_len:]
                            if new_part:
                                client._text_buffer = text
                                if client.events.on_text:
                                    await client.events.on_text(new_part)
                        else:
                            # New delta chunk - append to buffer
                            client._text_buffer += text
                            if client.events.on_text:
                                await client.events.on_text(text)

                elif "AgentThoughtChunk" in update_type:
                    content = getattr(update, "content", None)
                    if content and hasattr(content, "text"):
                        if client.events.on_thinking:
                            await client.events.on_thinking(content.text)

                elif "ToolCallStart" in update_type:
                    if client.events.on_tool_start:
                        await client.events.on_tool_start(
                            getattr(update, "tool_call_id", ""),
                            getattr(update, "title", ""),
                            getattr(update, "raw_input", {}),
                        )

                elif "ToolCallProgress" in update_type:
                    if client.events.on_tool_end:
                        await client.events.on_tool_end(
                            getattr(update, "tool_call_id", ""),
                            getattr(update, "status", ""),
                            getattr(update, "raw_output", None),
                        )

            async def request_permission(self, **kwargs: Any) -> dict:
                tool_call = kwargs.get("tool_call", {})
                name = tool_call.get("title", "Unknown")
                raw_input = tool_call.get("raw_input", {})

                approved = True
                if client.events.on_permission:
                    approved = await client.events.on_permission(name, raw_input)

                if approved:
                    return {"outcome": {"outcome": "selected", "option_id": "allow"}}
                return {"outcome": {"outcome": "selected", "option_id": "reject"}}

        return EventHandler()


__all__ = ["ClaudeClient", "ClaudeEvents"]
