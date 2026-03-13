"""Basic tests for WeCom AI Bot SDK"""

import asyncio
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from wecom_aibot_sdk import WSClient, generate_req_id, DefaultLogger
from wecom_aibot_sdk.types import WsFrame, WSClientOptions


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
