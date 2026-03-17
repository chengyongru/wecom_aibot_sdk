"""WebSocket long connection manager"""

import asyncio
import json
import time
from typing import Any, Optional

import websockets
from websockets.asyncio.client import ClientConnection
from websockets.protocol import State

from .types import WsFrame, WSClientOptions, CmdType
from .message_handler import MessageHandler
from .logger import Logger, DefaultLogger


class _ReplyQueueItem:
    """Reply queue item containing frame and future for ack waiting"""

    __slots__ = ("frame", "future")

    def __init__(self, frame: dict[str, Any], future: "asyncio.Future[WsFrame]"):
        self.frame = frame
        self.future = future


class WebSocketManager:
    """WebSocket connection manager with auto-reconnect and heartbeat"""

    DEFAULT_WS_URL = "wss://openws.work.weixin.qq.com"
    MAX_BACKOFF = 30000  # Max backoff interval: 30s

    def __init__(
        self,
        options: WSClientOptions,
        message_handler: MessageHandler,
        logger: Logger | None = None,
    ):
        self._options = options
        self._message_handler = message_handler
        self._logger = logger or DefaultLogger()

        self._ws: ClientConnection | None = None
        self._connected = False
        self._authenticated = False
        self._reconnect_attempts = 0
        self._heartbeat_task: asyncio.Task | None = None
        self._receive_task: asyncio.Task | None = None
        self._missed_pong_count = 0  # Consecutive missed pong count (official SDK naming)
        self._max_missed_pong = 2  # Max allowed consecutive missed pongs
        self._stop_event = asyncio.Event()
        self._kicked_by_new_connection = False  # Flag for disconnected_event

        # Serial reply queue (ported from official SDK)
        self._reply_queues: dict[str, list[_ReplyQueueItem]] = {}
        self._pending_acks: dict[
            str,
            tuple["asyncio.Future[WsFrame]", Optional[asyncio.TimerHandle]],
        ] = {}
        self._processing_queues: set[str] = set()  # req_ids being processed
        self._reply_ack_timeout: float = 5.0  # seconds
        self._max_reply_queue_size: int = 100

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected"""
        return self._connected and self._ws is not None and self._ws.state == State.OPEN

    async def connect(self) -> None:
        """Establish WebSocket connection"""
        if self._stop_event.is_set():
            self._stop_event.clear()

        # Reset kicked flag when manually connecting
        self._kicked_by_new_connection = False

        await self._do_connect()

    async def _do_connect(self) -> None:
        """Perform WebSocket connection"""
        # Reset kicked flag (for reconnect scenarios)
        self._kicked_by_new_connection = False

        # Stop old receive task first to prevent duplicate recv loops
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        # Close old WebSocket connection if exists
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                self._logger.debug(f"Error closing old WebSocket: {e}")
            self._ws = None

        ws_url = self._options.ws_url or self.DEFAULT_WS_URL

        try:
            self._ws = await websockets.connect(
                ws_url,
                ping_interval=None,  # We handle heartbeat ourselves
                ping_timeout=None,
            )
            self._connected = True
            self._logger.info("WebSocket connected")
            await self._message_handler.dispatch("connected", WsFrame(headers={"req_id": ""}))

            # Start receive loop immediately
            self._start_background_tasks()

            # Small delay to ensure receive loop is running
            await asyncio.sleep(0.1)

            # Send authentication
            await self._authenticate()

        except Exception as e:
            self._logger.error(f"WebSocket connection failed: {e}")
            self._connected = False
            raise

    async def _authenticate(self) -> None:
        """Send authentication frame"""
        auth_frame = {
            "cmd": CmdType.SUBSCRIBE,
            "headers": {"req_id": f"aibot_subscribe_{int(time.time() * 1000)}"},
            "body": {
                "bot_id": self._options.bot_id,
                "secret": self._options.secret,
            },
        }

        self._logger.debug(f"Sending auth frame: {auth_frame}")
        await self._send_raw(auth_frame)
        self._logger.debug("Authentication frame sent")

    async def disconnect(self) -> None:
        """Disconnect WebSocket"""
        self._stop_event.set()
        self._connected = False
        self._authenticated = False

        # Stop heartbeat task
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        # Stop receive task
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        # Clear pending messages and reply queues
        self._clear_pending_messages("Connection manually closed")

        # Close WebSocket
        if self._ws:
            await self._ws.close()
            self._ws = None

        self._logger.info("WebSocket disconnected")
        await self._message_handler.dispatch("disconnected", WsFrame(headers={"req_id": ""}, body="manual_disconnect"))

    def _start_background_tasks(self) -> None:
        """Start receive task (heartbeat starts after authentication)"""
        # Only create new task if not already running
        if self._receive_task is None or self._receive_task.done():
            self._receive_task = asyncio.create_task(self._receive_loop())

    def _start_heartbeat(self) -> None:
        """Start heartbeat task (called after successful authentication)"""
        self._stop_heartbeat()
        self._missed_pong_count = 0
        # Only create new task if not already running
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    def _stop_heartbeat(self) -> None:
        """Stop heartbeat task"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        """Heartbeat loop - aligned with official Node.js SDK implementation"""
        interval = self._options.heartbeat_interval / 1000

        while not self._stop_event.is_set() and self._connected:
            try:
                await asyncio.sleep(interval)

                if not self._connected or not self._ws:
                    break

                # Check for missing ACKs BEFORE sending (official SDK behavior)
                if self._missed_pong_count >= self._max_missed_pong:
                    self._logger.warn(
                        f"No heartbeat ack received for {self._missed_pong_count} consecutive pings"
                    )
                    await self._handle_disconnect("heartbeat_timeout")
                    break

                # Send heartbeat
                self._missed_pong_count += 1
                heartbeat_frame = {
                    "cmd": CmdType.HEARTBEAT,
                    "headers": {"req_id": f"ping_{int(time.time() * 1000)}"},
                }
                await self._send_raw(heartbeat_frame)
                self._logger.debug(
                    "Heartbeat sent, missed pong count: %d", self._missed_pong_count
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Heartbeat error: {e}")

    async def _receive_loop(self) -> None:
        """Receive loop for incoming messages"""
        self._logger.debug("Receive loop started")
        while not self._stop_event.is_set() and self._connected:
            try:
                if not self._ws:
                    self._logger.debug("No WebSocket, breaking receive loop")
                    break

                # Wait for message with timeout
                try:
                    message = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._logger.debug("No message in 5s, continuing...")
                    continue

                data = json.loads(message)
                self._logger.debug(f"Received: {data}")

                # Try to get req_id from headers first, then from top level
                # Note: headers might be None, so use or {} for safety
                headers = data.get("headers") or {}
                req_id = headers.get("req_id", "") or data.get("req_id", "")

                # Check if this is a reply ack
                if req_id and req_id in self._pending_acks:
                    self._handle_reply_ack(req_id, data)
                    continue

                if req_id.startswith("aibot_subscribe"):
                    if data.get("errcode") == 0:
                        self._authenticated = True
                        self._reconnect_attempts = 0
                        self._logger.info("Authenticated successfully")
                        # Start heartbeat after successful authentication (official SDK behavior)
                        self._start_heartbeat()
                        await self._message_handler.dispatch("authenticated", WsFrame(headers={"req_id": ""}))
                    else:
                        self._logger.error(f"Authentication failed: {data.get('errmsg')}")
                    continue

                # Handle heartbeat response (reset counter on success)
                if req_id.startswith("ping"):
                    if data.get("errcode") == 0:
                        self._missed_pong_count = 0  # Reset to 0 on successful pong (official SDK behavior)
                        self._logger.debug("Heartbeat ack received, reset missed pong count")
                    else:
                        self._logger.warn(f"Heartbeat ack error: {data.get('errmsg')}")
                    continue

                # Handle disconnected_event (kicked by new connection)
                # This is sent via aibot_event_callback before server closes connection
                body = data.get("body", {})
                if body.get("msgtype") == "event":
                    event = body.get("event", {})
                    # Support both eventtype (official) and event_type (legacy)
                    event_type = event.get("eventtype") or event.get("event_type")
                    if event_type == "disconnected_event":
                        self._logger.warn("Received disconnected_event, kicked by new connection")
                        self._kicked_by_new_connection = True
                        # Still dispatch the event for user handlers
                        frame = self._message_handler.parse_frame(data)
                        await self._message_handler.handle_frame(frame)
                        continue

                # Parse and handle frame
                frame = self._message_handler.parse_frame(data)
                await self._message_handler.handle_frame(frame)

            except websockets.ConnectionClosed as e:
                self._logger.warn(f"WebSocket connection closed: {e}")
                await self._handle_disconnect(f"connection_closed: {e.code}")
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Receive error: {e}")
                frame = WsFrame(headers={"req_id": ""}, body={"error": str(e)})
                await self._message_handler.dispatch("error", frame)
                break  # Exit loop to avoid conflict with potential reconnect

    async def _handle_disconnect(self, reason: str) -> None:
        """Handle disconnection and trigger reconnect"""
        self._connected = False
        self._authenticated = False

        # Clear pending messages before dispatching disconnected event
        self._clear_pending_messages(f"WebSocket disconnected ({reason})")

        await self._message_handler.dispatch("disconnected", WsFrame(headers={"req_id": ""}, body=reason))

        # Don't reconnect if kicked by new connection (disconnected_event)
        if self._kicked_by_new_connection:
            self._logger.info("Disconnected by new connection, not reconnecting")
            return

        # Attempt reconnect
        await self._reconnect()

    async def _reconnect(self) -> None:
        """Reconnect with exponential backoff"""
        max_attempts = self._options.max_reconnect_attempts

        while not self._stop_event.is_set():
            if max_attempts > 0 and self._reconnect_attempts >= max_attempts:
                self._logger.error("Max reconnect attempts reached")
                break

            # Calculate backoff
            backoff = min(
                self._options.reconnect_interval * (2**self._reconnect_attempts),
                self.MAX_BACKOFF,
            )

            self._reconnect_attempts += 1
            await self._message_handler.dispatch(
                "reconnecting", WsFrame(headers={"req_id": ""}, body={"attempt": self._reconnect_attempts})
            )

            self._logger.info(f"Reconnecting in {backoff}ms (attempt {self._reconnect_attempts})")
            await asyncio.sleep(backoff / 1000)

            try:
                await self._do_connect()
                self._logger.info("Reconnected successfully")
                return
            except Exception as e:
                self._logger.error(f"Reconnect attempt {self._reconnect_attempts} failed: {e}")

    async def _send_raw(self, data: dict[str, Any]) -> None:
        """Send raw JSON data"""
        if not self._ws or not self._connected:
            raise RuntimeError("WebSocket not connected")

        await self._ws.send(json.dumps(data))

    async def send(
        self,
        frame: WsFrame,
        body: dict[str, Any],
        cmd: str = CmdType.REPLY,
    ) -> WsFrame:
        """
        Send reply message through WebSocket with serial queue

        Messages with the same req_id are queued and sent serially,
        waiting for server ack before sending the next one.

        Args:
            frame: Original frame (for req_id)
            body: Message body
            cmd: Command type

        Returns:
            WsFrame: The ack frame from server
        """
        req_id = frame.headers["req_id"]
        return await self.send_reply(req_id, body, cmd)

    async def send_reply(
        self,
        req_id: str,
        body: dict[str, Any],
        cmd: str = CmdType.REPLY,
    ) -> WsFrame:
        """
        Send reply message through WebSocket (serial queue version)

        Messages with the same req_id are queued and sent serially.

        Args:
            req_id: The req_id from callback frame
            body: Reply message body
            cmd: Command type, defaults to CmdType.REPLY

        Returns:
            WsFrame: The ack frame from server
        """
        loop = asyncio.get_event_loop()
        future: "asyncio.Future[WsFrame]" = loop.create_future()

        frame: dict[str, Any] = {
            "cmd": cmd,
            "headers": {"req_id": req_id},
            "body": body,
        }

        item = _ReplyQueueItem(frame, future)

        if req_id not in self._reply_queues:
            self._reply_queues[req_id] = []

        queue = self._reply_queues[req_id]

        # Prevent queue from growing indefinitely
        if len(queue) >= self._max_reply_queue_size:
            self._logger.warn(
                f"Reply queue for req_id {req_id} exceeds max size ({self._max_reply_queue_size}), "
                "rejecting new message"
            )
            future.set_exception(
                RuntimeError(
                    f"Reply queue for req_id {req_id} exceeds max size ({self._max_reply_queue_size})"
                )
            )
            return await future

        queue.append(item)

        # If this is the only item in queue, start processing
        if len(queue) == 1 and req_id not in self._processing_queues:
            asyncio.ensure_future(self._process_reply_queue(req_id))

        return await future

    async def _process_reply_queue(self, req_id: str) -> None:
        """Process reply queue for a specific req_id"""
        self._processing_queues.add(req_id)

        try:
            while True:
                queue = self._reply_queues.get(req_id)
                if not queue:
                    self._reply_queues.pop(req_id, None)
                    break

                item = queue[0]

                # Send message first (official SDK behavior)
                try:
                    await self._send_raw(item.frame)
                    self._logger.debug(
                        f"Reply message sent via WebSocket, req_id: {req_id}, queue length: {len(queue)}"
                    )
                except Exception as e:
                    self._logger.error(f"Failed to send reply for req_id {req_id}: {e}")
                    queue.pop(0)
                    if not item.future.done():
                        item.future.set_exception(e)
                    continue

                # Wait for ack (set pending_acks AFTER sending - official SDK behavior)
                loop = asyncio.get_event_loop()
                ack_future: "asyncio.Future[WsFrame]" = loop.create_future()

                # Set timeout
                timeout_handle = loop.call_later(
                    self._reply_ack_timeout,
                    self._on_reply_ack_timeout,
                    req_id,
                    ack_future,
                )

                self._pending_acks[req_id] = (ack_future, timeout_handle)

                try:
                    ack_frame = await ack_future
                    # Successfully received ack
                    queue.pop(0)
                    if not item.future.done():
                        item.future.set_result(ack_frame)
                except Exception as e:
                    queue.pop(0)
                    if not item.future.done():
                        item.future.set_exception(e)
        finally:
            self._processing_queues.discard(req_id)

    def _on_reply_ack_timeout(
        self, req_id: str, ack_future: "asyncio.Future[WsFrame]"
    ) -> None:
        """Reply ack timeout callback"""
        self._logger.warn(
            f"Reply ack timeout ({self._reply_ack_timeout}s) for req_id: {req_id}"
        )
        self._pending_acks.pop(req_id, None)
        if not ack_future.done():
            ack_future.set_exception(
                TimeoutError(
                    f"Reply ack timeout ({self._reply_ack_timeout}s) for req_id: {req_id}"
                )
            )

    def _handle_reply_ack(self, req_id: str, frame: dict[str, Any]) -> None:
        """Handle reply message ack"""
        pending = self._pending_acks.pop(req_id, None)
        if not pending:
            return

        ack_future, timeout_handle = pending

        # Cancel timeout
        if timeout_handle:
            timeout_handle.cancel()

        errcode = frame.get("errcode")
        if errcode != 0:
            self._logger.warn(
                f"Reply ack error: req_id={req_id}, errcode={errcode}, errmsg={frame.get('errmsg')}"
            )
            if not ack_future.done():
                ack_future.set_exception(
                    RuntimeError(
                        f"Reply ack error: errcode={errcode}, errmsg={frame.get('errmsg')}"
                    )
                )
        else:
            self._logger.debug(f"Reply ack received for req_id: {req_id}")
            if not ack_future.done():
                # Convert dict to WsFrame
                ws_frame = WsFrame(
                    cmd=frame.get("cmd"),
                    headers=frame.get("headers", {}),
                    body=frame.get("body"),
                    errcode=frame.get("errcode"),
                    errmsg=frame.get("errmsg"),
                )
                ack_future.set_result(ws_frame)

    def _clear_pending_messages(self, reason: str) -> None:
        """Clear all pending messages and acks"""
        for req_id, (ack_future, timeout_handle) in self._pending_acks.items():
            if timeout_handle:
                timeout_handle.cancel()
            if not ack_future.done():
                ack_future.set_exception(RuntimeError(reason))
        self._pending_acks.clear()

        for req_id, queue in self._reply_queues.items():
            for item in queue:
                if not item.future.done():
                    item.future.set_exception(
                        RuntimeError(f"{reason}, reply for req_id: {req_id} cancelled")
                    )
        self._reply_queues.clear()
        self._processing_queues.clear()
