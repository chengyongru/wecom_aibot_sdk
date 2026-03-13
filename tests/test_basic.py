"""Basic tests for WeCom AI Bot SDK"""

import asyncio
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from wecom_aibot_sdk import WSClient, generate_req_id, DefaultLogger
from wecom_aibot_sdk.types import WsFrame, WSClientOptions, WSClientOptions as WSOptions


class TestGenerateReqId:
    def test_without_prefix(self):
        req_id = generate_req_id()
        assert len(req_id) == 16
        assert req_id.isalnum()

    def test_with_prefix(self):
        req_id = generate_req_id("stream")
        assert req_id.startswith("stream_")
        assert len(req_id) == 23  # "stream_" (7) + 16 chars


class TestDefaultLogger:
    def test_debug(self, caplog):
        """Test debug logging with DEBUG level"""
        logger = DefaultLogger(level=logging.DEBUG)
        logger.debug("test message %s", "arg")
        # caplog captures logging output
        assert "DEBUG" in caplog.text
        assert "test message arg" in caplog.text

    def test_info(self, caplog):
        """Test info logging with INFO level"""
        logger = DefaultLogger(level=logging.INFO)
        logger.info("info test")
        assert "INFO" in caplog.text
        assert "info test" in caplog.text

    def test_warn(self, caplog):
        """Test warn logging (default level WARNING)"""
        logger = DefaultLogger()
        logger.warn("warning test")
        assert "WARNING" in caplog.text
        assert "warning test" in caplog.text

    def test_error(self, caplog):
        """Test error logging (default level includes ERROR)"""
        logger = DefaultLogger()
        logger.error("error test")
        assert "ERROR" in caplog.text
        assert "error test" in caplog.text


class TestWSClient:
    def test_init_with_dict(self):
        client = WSClient({
            "bot_id": "test_bot",
            "secret": "test_secret",
        })
        assert client._options.bot_id == "test_bot"
        assert client._options.secret == "test_secret"

    def test_init_with_dataclass(self):
        options = WSClientOptions(bot_id="test", secret="secret")
        client = WSClient(options)
        assert client._options.bot_id == "test"

    def test_is_connected_initial(self):
        client = WSClient({"bot_id": "test", "secret": "secret"})
        assert client.is_connected is False

    def test_event_handler_registration(self):
        client = WSClient({"bot_id": "test", "secret": "secret"})

        async def handler(frame):
            pass

        client.on("message.text", handler)
        assert "message.text" in client._message_handler._event_handlers
        assert handler in client._message_handler._event_handlers["message.text"]

    def test_event_handler_removal(self):
        client = WSClient({"bot_id": "test", "secret": "secret"})

        async def handler(frame):
            pass

        client.on("message.text", handler)
        client.off("message.text", handler)
        assert handler not in client._message_handler._event_handlers.get("message.text", [])


class TestWsFrame:
    def test_frame_creation(self):
        frame = WsFrame(
            headers={"req_id": "test123"},
            cmd="test",
            body={"data": "value"},
        )
        assert frame.headers["req_id"] == "test123"
        assert frame.cmd == "test"
        assert frame.body == {"data": "value"}

    def test_frame_defaults(self):
        frame = WsFrame(headers={"req_id": "test"})
        assert frame.cmd is None
        assert frame.body is None
        assert frame.errcode is None


class TestCrypto:
    def test_decrypt_file(self):
        """Test AES-256-CBC file decryption with 32-byte PKCS#7 padding"""
        from wecom_aibot_sdk.crypto import decrypt_file
        import base64
        from Crypto.Cipher import AES

        # Test data
        key = b"A" * 32  # 32 bytes for AES-256
        iv = key[:16]  # IV is first 16 bytes of key (WeCom convention)
        plaintext = b"Hello, World!"

        # Manual PKCS#7 padding to 32-byte boundary (WeCom specification)
        pad_len = 32 - (len(plaintext) % 32)
        padded_plaintext = plaintext + bytes([pad_len] * pad_len)

        # Encrypt
        cipher = AES.new(key, AES.MODE_CBC, iv)
        ciphertext = cipher.encrypt(padded_plaintext)
        # WeCom API returns base64 encoded ciphertext (IV is derived from key, not prepended)
        encrypted_data_b64 = base64.b64encode(ciphertext).decode()

        # Decrypt using our function
        aes_key_b64 = base64.b64encode(key).decode()
        decrypted = decrypt_file(encrypted_data_b64, aes_key_b64)

        assert decrypted == plaintext

    def test_extract_filename(self):
        from wecom_aibot_sdk.crypto import extract_filename

        header = 'attachment; filename="test.png"'
        assert extract_filename(header) == "test.png"

        header = 'filename="report.pdf"'
        assert extract_filename(header) == "report.pdf"

        assert extract_filename("no filename") == "unknown_file"


class TestMessageHandler:
    @pytest.mark.asyncio
    async def test_dispatch_message(self):
        from wecom_aibot_sdk.message_handler import MessageHandler

        handler = MessageHandler()
        received = []

        async def on_message(frame):
            received.append(frame)

        handler.on("message", on_message)

        frame = WsFrame(headers={"req_id": "test"}, body={"msgtype": "text"})
        await handler.dispatch("message", frame)

        assert len(received) == 1
        assert received[0] == frame

    @pytest.mark.asyncio
    async def test_handle_text_message(self):
        from wecom_aibot_sdk.message_handler import MessageHandler

        handler = MessageHandler()
        received = []

        async def on_text(frame):
            received.append(frame)

        handler.on("message.text", on_text)

        frame = WsFrame(
            headers={"req_id": "test"},
            body={"msgtype": "text", "text": {"content": "hello"}}
        )
        await handler.handle_frame(frame)

        assert len(received) == 1


class TestEventTypeCompatibility:
    """Test event type field name compatibility (eventtype vs event_type)"""

    @pytest.mark.asyncio
    async def test_eventtype_field(self):
        """Test event handling with official 'eventtype' field"""
        from wecom_aibot_sdk.message_handler import MessageHandler

        handler = MessageHandler()
        received = []

        async def on_enter(frame):
            received.append(frame)

        handler.on("event.enter_chat", on_enter)

        frame = WsFrame(
            headers={"req_id": "test"},
            body={
                "msgtype": "event",
                "event": {"eventtype": "enter_chat"}
            }
        )
        await handler.handle_frame(frame)

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_event_type_field(self):
        """Test event handling with legacy 'event_type' field"""
        from wecom_aibot_sdk.message_handler import MessageHandler

        handler = MessageHandler()
        received = []

        async def on_enter(frame):
            received.append(frame)

        handler.on("event.enter_chat", on_enter)

        frame = WsFrame(
            headers={"req_id": "test"},
            body={
                "msgtype": "event",
                "event": {"event_type": "enter_chat"}
            }
        )
        await handler.handle_frame(frame)

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_disconnected_event(self):
        """Test disconnected_event handling"""
        from wecom_aibot_sdk.message_handler import MessageHandler

        handler = MessageHandler()
        received = []

        async def on_disconnected(frame):
            received.append(frame)

        handler.on("event.disconnected_event", on_disconnected)

        frame = WsFrame(
            headers={"req_id": "test"},
            body={
                "msgtype": "event",
                "event": {"eventtype": "disconnected_event"}
            }
        )
        await handler.handle_frame(frame)

        assert len(received) == 1


class TestWebSocketManager:
    """Test WebSocketManager reconnection behavior"""

    @pytest.mark.asyncio
    async def test_kicked_flag_prevents_reconnect(self):
        """Test that _kicked_by_new_connection flag prevents auto-reconnect"""
        from wecom_aibot_sdk.ws import WebSocketManager
        from wecom_aibot_sdk.message_handler import MessageHandler

        options = WSOptions(
            bot_id="test",
            secret="test",
            max_reconnect_attempts=3,
        )
        handler = MessageHandler()
        manager = WebSocketManager(options, handler)

        # Set the kicked flag
        manager._kicked_by_new_connection = True
        manager._connected = False

        # Call _handle_disconnect - should NOT trigger reconnect
        await manager._handle_disconnect("test_disconnect")

        # Verify reconnect was NOT attempted
        assert manager._reconnect_attempts == 0

    @pytest.mark.asyncio
    async def test_kicked_flag_reset_on_connect(self):
        """Test that _kicked_by_new_connection flag is reset on connect"""
        from wecom_aibot_sdk.ws import WebSocketManager
        from wecom_aibot_sdk.message_handler import MessageHandler

        options = WSOptions(
            bot_id="test",
            secret="test",
        )
        handler = MessageHandler()
        manager = WebSocketManager(options, handler)

        # Set the kicked flag
        manager._kicked_by_new_connection = True

        # Reset flag via connect method
        manager._stop_event.set()
        await manager.connect()

        # Verify flag was reset
        assert manager._kicked_by_new_connection == False

    @pytest.mark.asyncio
    async def test_receive_loop_cancellation(self):
        """Test that old receive task is cancelled before creating new one"""
        from wecom_aibot_sdk.ws import WebSocketManager
        from wecom_aibot_sdk.message_handler import MessageHandler

        options = WSOptions(
            bot_id="test",
            secret="test",
        )
        handler = MessageHandler()
        manager = WebSocketManager(options, handler)

        # Create a fake running task
        async def fake_loop():
            await asyncio.sleep(10)

        manager._receive_task = asyncio.create_task(fake_loop())

        # Mock websockets.connect and _authenticate
        mock_ws = MagicMock()
        mock_ws.state = MagicMock()
        mock_ws.state.name = "OPEN"

        with patch('wecom_aibot_sdk.ws.websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_ws

            with patch.object(manager, '_authenticate', new_callable=AsyncMock):
                with patch.object(manager, '_start_background_tasks'):
                    try:
                        await manager._do_connect()
                    except Exception:
                        pass

        # Verify old task was cancelled (either done or None)
        assert manager._receive_task is None or manager._receive_task.done()
