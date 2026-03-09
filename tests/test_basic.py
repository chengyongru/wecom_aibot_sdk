"""Basic tests for WeCom AI Bot SDK"""

import asyncio
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
    def test_debug(self, capsys):
        logger = DefaultLogger()
        logger.debug("test message %s", "arg")
        captured = capsys.readouterr()
        assert "[DEBUG]" in captured.out
        assert "test message arg" in captured.out

    def test_info(self, capsys):
        logger = DefaultLogger()
        logger.info("info test")
        captured = capsys.readouterr()
        assert "[INFO]" in captured.out

    def test_warn(self, capsys):
        logger = DefaultLogger()
        logger.warn("warning test")
        captured = capsys.readouterr()
        assert "[WARN]" in captured.out

    def test_error(self, capsys):
        logger = DefaultLogger()
        logger.error("error test")
        captured = capsys.readouterr()
        assert "[ERROR]" in captured.out


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
        from wecom_aibot_sdk.crypto import decrypt_file
        import base64
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad

        # Test data
        key = b"A" * 32  # 32 bytes for AES-256
        iv = b"B" * 16
        plaintext = b"Hello, World!"

        # Encrypt
        cipher = AES.new(key, AES.MODE_CBC, iv)
        ciphertext = cipher.encrypt(pad(plaintext, AES.block_size))
        encrypted_data = iv + ciphertext

        # Decrypt using our function
        aes_key_b64 = base64.b64encode(key).decode()
        decrypted = decrypt_file(encrypted_data, aes_key_b64)

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
