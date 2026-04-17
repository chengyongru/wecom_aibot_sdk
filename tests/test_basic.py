"""Basic tests for WeCom AI Bot SDK"""

import asyncio
import logging
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from wecom_aibot_sdk import WSClient, generate_req_id, DefaultLogger
from wecom_aibot_sdk.types import WsFrame, WSClientOptions, WSClientOptions as WSOptions
from wecom_aibot_sdk.upload import (
    _sanitize_filename,
    _guess_wecom_media_type,
    _validate_upload_file,
    _chunk_data,
    WECOM_UPLOAD_CHUNK_SIZE,
)


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

        # Wait for async task to complete
        await asyncio.sleep(0.1)

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

        # Wait for async task to complete
        await asyncio.sleep(0.1)

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

        # Wait for async task to complete
        await asyncio.sleep(0.1)

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

        # Wait for async task to complete
        await asyncio.sleep(0.1)

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

        # Wait for async task to complete
        await asyncio.sleep(0.1)

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


# ── Fake WebSocket manager for upload tests ──

class _FakeWsManager:
    """Minimal fake WebSocketManager that records send_reply calls."""

    def __init__(self, responses: list[WsFrame] | None = None):
        self.calls: list[tuple[str, dict, str]] = []
        self._responses = responses or []
        self._idx = 0

    def _next_response(self, req_id: str) -> WsFrame:
        if self._idx < len(self._responses):
            resp = self._responses[self._idx]
            self._idx += 1
            return resp
        return WsFrame(headers={"req_id": req_id}, errcode=0, body={})

    async def send_reply(self, req_id: str, body: dict, cmd: str) -> WsFrame:
        self.calls.append((req_id, body, cmd))
        return self._next_response(req_id)

    async def send(self, frame: WsFrame, body: dict, cmd: str) -> WsFrame:
        req_id = frame.headers.get("req_id", "")
        self.calls.append((req_id, body, cmd))
        return self._next_response(req_id)


class TestUploadHelpers:
    """Test pure helper functions in upload.py"""

    def test_sanitize_filename_strips_path(self):
        assert _sanitize_filename("/tmp/dir/photo.png") == "photo.png"

    def test_sanitize_filename_replaces_unsafe_chars(self):
        assert _sanitize_filename("my file (1).jpg") == "my_file__1_.jpg"

    def test_sanitize_filename_keeps_safe_chars(self):
        assert _sanitize_filename("report-2025_v1.2.pdf") == "report-2025_v1.2.pdf"

    def test_guess_image(self):
        for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
            assert _guess_wecom_media_type(f"test{ext}") == "image"

    def test_guess_video(self):
        for ext in (".mp4", ".avi", ".mov"):
            assert _guess_wecom_media_type(f"test{ext}") == "video"

    def test_guess_voice(self):
        for ext in (".amr", ".mp3", ".wav", ".ogg"):
            assert _guess_wecom_media_type(f"test{ext}") == "voice"

    def test_guess_file_fallback(self):
        assert _guess_wecom_media_type("archive.zip") == "file"

    def test_validate_upload_file_success(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG" + b"\x00" * 100)
            f.flush()
            name, media_type, size = _validate_upload_file(f.name)
        os.unlink(f.name)
        assert media_type == "image"
        assert size == 104

    def test_validate_upload_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            _validate_upload_file("/nonexistent/file.txt")

    def test_validate_upload_file_too_large(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"x")
            f.flush()
            with patch("wecom_aibot_sdk.upload.WECOM_UPLOAD_MAX_BYTES", 0):
                with pytest.raises(ValueError, match="too large"):
                    _validate_upload_file(f.name)
        os.unlink(f.name)

    def test_chunk_data(self):
        data = b"A" * 1000
        chunks = _chunk_data(data, 300)
        assert len(chunks) == 4
        assert len(chunks[0]) == 300
        assert len(chunks[-1]) == 100
        assert b"".join(chunks) == data

    def test_chunk_data_empty(self):
        assert _chunk_data(b"") == []

    def test_chunk_data_default_size(self):
        data = b"x" * (WECOM_UPLOAD_CHUNK_SIZE + 1)
        chunks = _chunk_data(data)
        assert len(chunks) == 2
        assert len(chunks[0]) == WECOM_UPLOAD_CHUNK_SIZE
        assert len(chunks[1]) == 1


class TestUploadMedia:
    """Test WSClient.upload_media flow with mocked ws_manager"""

    @pytest.fixture
    def client_with_fake_ws(self):
        client = WSClient({"bot_id": "test", "secret": "test"})
        return client

    def _make_upload_file(self, suffix=".png", size=100):
        f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        f.write(b"\x00" * size)
        f.flush()
        f.close()
        return f.name

    @pytest.mark.asyncio
    async def test_upload_media_success_single_chunk(self, client_with_fake_ws):
        path = self._make_upload_file()
        try:
            fake = _FakeWsManager([
                WsFrame(headers={"req_id": ""}, errcode=0, body={"upload_id": "uid123"}),
                WsFrame(headers={"req_id": ""}, errcode=0, body={}),
                WsFrame(headers={"req_id": ""}, errcode=0, body={"media_id": "mid_abc"}),
            ])
            client_with_fake_ws._ws_manager = fake

            result = await client_with_fake_ws.upload_media(path)
            assert result.media_id == "mid_abc"
            assert result.media_type == "image"
            assert len(fake.calls) == 3
            assert fake.calls[0][2] == "aibot_upload_media_init"
            assert fake.calls[1][2] == "aibot_upload_media_chunk"
            assert fake.calls[2][2] == "aibot_upload_media_finish"
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_upload_media_multiple_chunks(self, client_with_fake_ws):
        path = self._make_upload_file(size=700)
        try:
            fake = _FakeWsManager([
                WsFrame(headers={"req_id": ""}, errcode=0, body={"upload_id": "uid"}),
                # 2 chunk acks (700 bytes / 512 bytes per chunk = 2 chunks)
                WsFrame(headers={"req_id": ""}, errcode=0, body={}),
                WsFrame(headers={"req_id": ""}, errcode=0, body={}),
                WsFrame(headers={"req_id": ""}, errcode=0, body={"media_id": "mid"}),
            ])
            client_with_fake_ws._ws_manager = fake

            # Patch the WECOM_UPLOAD_CHUNK_SIZE used by client._chunk_data
            with patch("wecom_aibot_sdk.client.WECOM_UPLOAD_CHUNK_SIZE", 512):
                result = await client_with_fake_ws.upload_media(path)
            assert result.media_id == "mid"
            assert len(fake.calls) == 4  # init + 2 chunks + finish
            # Verify chunk_index values
            assert fake.calls[1][1]["chunk_index"] == 0
            assert fake.calls[1][1]["total_chunks"] == 2
            assert fake.calls[2][1]["chunk_index"] == 1
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_upload_media_init_failure(self, client_with_fake_ws):
        path = self._make_upload_file()
        try:
            fake = _FakeWsManager([
                WsFrame(headers={"req_id": ""}, errcode=40001, errmsg="init failed", body={}),
            ])
            client_with_fake_ws._ws_manager = fake

            with pytest.raises(RuntimeError, match="upload_init failed"):
                await client_with_fake_ws.upload_media(path)
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_upload_media_chunk_failure(self, client_with_fake_ws):
        path = self._make_upload_file()
        try:
            fake = _FakeWsManager([
                WsFrame(headers={"req_id": ""}, errcode=0, body={"upload_id": "uid"}),
                WsFrame(headers={"req_id": ""}, errcode=50001, errmsg="chunk fail", body={}),
            ])
            client_with_fake_ws._ws_manager = fake

            with pytest.raises(RuntimeError, match="upload_chunk"):
                await client_with_fake_ws.upload_media(path)
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_upload_media_finish_failure(self, client_with_fake_ws):
        path = self._make_upload_file()
        try:
            fake = _FakeWsManager([
                WsFrame(headers={"req_id": ""}, errcode=0, body={"upload_id": "uid"}),
                WsFrame(headers={"req_id": ""}, errcode=0, body={}),
                WsFrame(headers={"req_id": ""}, errcode=60001, errmsg="finish fail", body={}),
            ])
            client_with_fake_ws._ws_manager = fake

            with pytest.raises(RuntimeError, match="upload_finish failed"):
                await client_with_fake_ws.upload_media(path)
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_upload_media_empty_upload_id(self, client_with_fake_ws):
        path = self._make_upload_file()
        try:
            fake = _FakeWsManager([
                WsFrame(headers={"req_id": ""}, errcode=0, body={}),  # no upload_id
            ])
            client_with_fake_ws._ws_manager = fake

            with pytest.raises(RuntimeError, match="no upload_id"):
                await client_with_fake_ws.upload_media(path)
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_upload_media_empty_media_id(self, client_with_fake_ws):
        path = self._make_upload_file()
        try:
            fake = _FakeWsManager([
                WsFrame(headers={"req_id": ""}, errcode=0, body={"upload_id": "uid"}),
                WsFrame(headers={"req_id": ""}, errcode=0, body={}),
                WsFrame(headers={"req_id": ""}, errcode=0, body={}),  # no media_id
            ])
            client_with_fake_ws._ws_manager = fake

            with pytest.raises(RuntimeError, match="no media_id"):
                await client_with_fake_ws.upload_media(path)
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_upload_media_file_not_found(self, client_with_fake_ws):
        with pytest.raises(FileNotFoundError):
            await client_with_fake_ws.upload_media("/nonexistent/file.png")

    @pytest.mark.asyncio
    async def test_upload_media_file_too_large(self, client_with_fake_ws):
        path = self._make_upload_file()
        try:
            fake = _FakeWsManager()
            client_with_fake_ws._ws_manager = fake

            with patch("wecom_aibot_sdk.upload.WECOM_UPLOAD_MAX_BYTES", 0):
                with pytest.raises(ValueError, match="too large"):
                    await client_with_fake_ws.upload_media(path)
        finally:
            os.unlink(path)


class TestReplyMedia:
    """Test reply_media and send_media_message"""

    @pytest.fixture
    def client(self):
        return WSClient({"bot_id": "test", "secret": "test"})

    def _make_upload_file(self, suffix=".png", size=100):
        f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        f.write(b"\x00" * size)
        f.flush()
        f.close()
        return f.name

    @pytest.mark.asyncio
    async def test_reply_media(self, client):
        path = self._make_upload_file()
        try:
            upload_responses = [
                WsFrame(headers={"req_id": ""}, errcode=0, body={"upload_id": "uid"}),
                WsFrame(headers={"req_id": ""}, errcode=0, body={}),
                WsFrame(headers={"req_id": ""}, errcode=0, body={"media_id": "mid123"}),
            ]
            # 4th response is for the reply() call
            reply_ack = WsFrame(headers={"req_id": ""}, errcode=0, body={})
            fake = _FakeWsManager(upload_responses + [reply_ack])
            client._ws_manager = fake

            frame = WsFrame(headers={"req_id": "orig_req"})
            ack = await client.reply_media(frame, path)
            assert ack.errcode == 0

            # Last call should be the reply with media body
            last_body = fake.calls[-1][1]
            assert last_body["msgtype"] == "image"
            assert last_body["image"]["media_id"] == "mid123"
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_send_media_message(self, client):
        path = self._make_upload_file(suffix=".mp4", size=200)
        try:
            upload_responses = [
                WsFrame(headers={"req_id": ""}, errcode=0, body={"upload_id": "uid"}),
                WsFrame(headers={"req_id": ""}, errcode=0, body={}),
                WsFrame(headers={"req_id": ""}, errcode=0, body={"media_id": "vid_mid"}),
            ]
            send_ack = WsFrame(headers={"req_id": ""}, errcode=0, body={})
            fake = _FakeWsManager(upload_responses + [send_ack])
            client._ws_manager = fake

            ack = await client.send_media_message("chat_001", path)
            assert ack.errcode == 0

            last_body = fake.calls[-1][1]
            assert last_body["chatid"] == "chat_001"
            assert last_body["msgtype"] == "video"
            assert last_body["video"]["media_id"] == "vid_mid"
        finally:
            os.unlink(path)
