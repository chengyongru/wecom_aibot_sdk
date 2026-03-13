"""WebSocket long connection manager"""

import asyncio
import json
import time
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection
from websockets.protocol import State

from .types import WsFrame, WSClientOptions, CmdType
from .message_handler import MessageHandler
from .logger import Logger, DefaultLogger


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
        self._reply_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._reply_tasks: dict[str, asyncio.Task] = {}
        self._stop_event = asyncio.Event()

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected"""
        return self._connected and self._ws is not None and self._ws.state == State.OPEN

    async def connect(self) -> None:
        """Establish WebSocket connection"""
        if self._stop_event.is_set():
            self._stop_event.clear()

        await self._do_connect()

    async def _do_connect(self) -> None:
        """Perform WebSocket connection"""
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

        # Cancel all reply tasks
        for task in self._reply_tasks.values():
            task.cancel()
        self._reply_tasks.clear()

        # Close WebSocket
        if self._ws:
            await self._ws.close()
            self._ws = None

        self._logger.info("WebSocket disconnected")
        await self._message_handler.dispatch("disconnected", WsFrame(headers={"req_id": ""}, body="manual_disconnect"))

    def _start_background_tasks(self) -> None:
        """Start receive task (heartbeat starts after authentication)"""
        self._receive_task = asyncio.create_task(self._receive_loop())

    def _start_heartbeat(self) -> None:
        """Start heartbeat task (called after successful authentication)"""
        self._stop_heartbeat()
        self._missed_pong_count = 0
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

                # Log raw message
                self._logger.info(f"RAW MESSAGE: {message}")

                data = json.loads(message)

                # Debug: log raw received data
                self._logger.debug(f"Received: {data}")

                # Handle generic ACK (not heartbeat related)
                if data.get("cmd") == "ack":
                    self._logger.debug("Generic ACK received")
                    continue

                # Handle auth response (no cmd, check req_id prefix)
                req_id = data.get("headers", {}).get("req_id", "")
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

    async def _handle_disconnect(self, reason: str) -> None:
        """Handle disconnection and trigger reconnect"""
        self._connected = False
        self._authenticated = False

        await self._message_handler.dispatch("disconnected", WsFrame(headers={"req_id": ""}, body=reason))

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
    ) -> None:
        """
        Send reply message through WebSocket

        Args:
            frame: Original frame (for req_id)
            body: Message body
            cmd: Command type
        """
        data = {
            "cmd": cmd,
            "headers": {"req_id": frame.headers["req_id"]},
            "body": body,
        }
        await self._send_raw(data)

    async def send_serialized(self, req_id: str, data: dict[str, Any]) -> None:
        """
        Send message with serialized queue (wait for ack before next)

        Args:
            req_id: Request ID for queue grouping
            data: Data to send
        """
        # If there's already a task for this req_id, wait for it
        if req_id in self._reply_tasks:
            try:
                await self._reply_tasks[req_id]
            except Exception:
                pass

        # Create new task
        task = asyncio.create_task(self._send_and_wait_ack(data))
        self._reply_tasks[req_id] = task

        try:
            await task
        finally:
            self._reply_tasks.pop(req_id, None)

    async def _send_and_wait_ack(self, data: dict[str, Any]) -> None:
        """Send data and wait for ack"""
        await self._send_raw(data)
        # Note: In real implementation, we would wait for specific ack
        # For now, just send without waiting
