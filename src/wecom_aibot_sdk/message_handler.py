"""Message parsing and event dispatching"""

import asyncio
from typing import Any, Callable, Awaitable

from .types import WsFrame, MessageType, EventType
from .logger import Logger, DefaultLogger


# Event callback type
EventHandler = Callable[[WsFrame], Awaitable[None]]


class MessageHandler:
    """Message parser and event dispatcher"""

    def __init__(self, logger: Logger | None = None):
        self._logger = logger or DefaultLogger()
        self._event_handlers: dict[str, list[EventHandler]] = {}

    def on(self, event: str, handler: EventHandler) -> None:
        """Register event handler"""
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    def off(self, event: str, handler: EventHandler | None = None) -> None:
        """Remove event handler(s)"""
        if event not in self._event_handlers:
            return
        if handler is None:
            self._event_handlers[event] = []
        else:
            self._event_handlers[event] = [h for h in self._event_handlers[event] if h != handler]

    async def dispatch(self, event: str, frame: WsFrame) -> None:
        """
        Dispatch event to handlers (non-blocking)

        Handlers are executed in separate tasks to avoid blocking the receive loop.
        This allows handlers to await reply methods while the receive loop continues
        to process incoming ack frames.
        """
        handlers = self._event_handlers.get(event, [])
        for handler in handlers:
            try:
                # Use create_task to avoid blocking the receive loop
                asyncio.create_task(self._run_handler(handler, event, frame))
            except Exception as e:
                self._logger.error(f"Error creating task for event '{event}': {e}")

        # Also dispatch to wildcard handlers
        if event != "*":
            wildcard_handlers = self._event_handlers.get("*", [])
            for handler in wildcard_handlers:
                try:
                    asyncio.create_task(self._run_handler(handler, "*", frame))
                except Exception as e:
                    self._logger.error(f"Error creating wildcard handler task: {e}")

    async def _run_handler(self, handler: EventHandler, event: str, frame: WsFrame) -> None:
        """Run a single handler with error handling"""
        try:
            await handler(frame)
        except Exception as e:
            self._logger.error(f"Error in handler for event '{event}': {e}")

    def parse_frame(self, data: dict[str, Any]) -> WsFrame:
        """Parse raw WebSocket data into WsFrame"""
        headers = data.get("headers", {})
        if "req_id" not in headers:
            headers["req_id"] = ""

        frame = WsFrame(
            cmd=data.get("cmd"),
            headers=headers,
            body=data.get("body"),
            errcode=data.get("errcode"),
            errmsg=data.get("errmsg"),
        )
        return frame

    async def handle_frame(self, frame: WsFrame) -> None:
        """Handle incoming frame and dispatch appropriate events"""
        body = frame.body
        if not body or not isinstance(body, dict):
            return

        msgtype = body.get("msgtype")

        if msgtype == "event":
            # Handle event message
            event = body.get("event", {})
            # Support both eventtype (official API) and event_type (legacy)
            event_type = (event.get("eventtype") or event.get("event_type")) if isinstance(event, dict) else None

            # Dispatch general event
            await self.dispatch("event", frame)

            # Dispatch specific event
            if event_type:
                await self.dispatch(f"event.{event_type}", frame)

        elif msgtype:
            # Handle message
            await self.dispatch("message", frame)

            # Dispatch specific message type
            if msgtype in [mt.value for mt in MessageType]:
                await self.dispatch(f"message.{msgtype}", frame)
