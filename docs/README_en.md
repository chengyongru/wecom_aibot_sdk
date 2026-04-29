# WeCom AI Bot Python SDK

[![PyPI version](https://img.shields.io/pypi/v/wecom-aibot-sdk-python)](https://pypi.org/project/wecom-aibot-sdk-python/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[简体中文](../README.md)

Enterprise WeChat AI Bot Python SDK - Based on WebSocket long connection, providing message sending/receiving, streaming replies, template cards, event callbacks, file download/decryption, media file upload and other core capabilities.

## Features

- **WebSocket Long Connection** - Built-in default address `wss://openws.work.weixin.qq.com`, ready to use
- **Auto Authentication** - Automatically sends authentication frame after connection (botId + secret)
- **Heartbeat Keep-Alive** - Automatic heartbeat maintenance, auto-detects connection issues when ACKs are missing
- **Auto Reconnect** - Exponential backoff reconnection strategy (1s → 2s → 4s → ... → 30s max)
- **Message Dispatch** - Auto-parses message types and triggers corresponding events (text/image/mixed/voice/file)
- **Streaming Reply** - Built-in streaming reply methods, supports Markdown and mixed content
- **Template Cards** - Supports replying with template card messages, stream+card combo replies, card updates
- **Proactive Push** - Proactively send Markdown or template card messages to specified chats
- **Event Callbacks** - Supports enter_chat, template_card_event, feedback_event
- **Serial Reply Queue** - Replies with same req_id are sent serially, auto-waits for receipt
- **File Download & Decryption** - Built-in AES-256-CBC file decryption, supports RFC 5987 filename encoding
- **Media File Upload** - Upload images/videos/voice/files via WebSocket 3-step protocol (init → chunk × N → finish)
- **Pluggable Logging** - Uses Python's built-in `logging` module, defaults to WARNING level

## Installation

```bash
pip install wecom-aibot-sdk-python
```

## Quick Start

```python
import asyncio
from wecom_aibot_sdk import WSClient, generate_req_id

async def main():
    # 1. Create client instance
    client = WSClient({
        "bot_id": "your-bot-id",
        "secret": "your-bot-secret",
    })

    # 2. Listen for text messages and reply with streaming
    async def on_text(frame):
        content = frame.body.get("text", {}).get("content", "")
        stream_id = generate_req_id("stream")

        # Send intermediate content
        await client.reply_stream(frame, stream_id, "Thinking...", finish=False)

        # Send final result
        await client.reply_stream(frame, stream_id, f'You said: "{content}"', finish=True)

    client.on("message.text", on_text)

    # 3. Listen for enter_chat event (send welcome)
    async def on_enter(frame):
        await client.reply_welcome(frame, {
            "msgtype": "text",
            "text": {"content": "Hello! How can I help you?"},
        })

    client.on("event.enter_chat", on_enter)

    # 4. Connect
    await client.connect_async()

    # Keep running
    while client.is_connected:
        await asyncio.sleep(1)

asyncio.run(main())
```

## API Reference

### WSClient

Core client class providing connection management, message sending/receiving.

```python
client = WSClient({
    "bot_id": "your-bot-id",
    "secret": "your-bot-secret",
    # Optional:
    "reconnect_interval": 1000,     # Reconnect base delay (ms)
    "max_reconnect_attempts": 10,   # Max reconnect attempts (-1 for infinite)
    "heartbeat_interval": 30000,    # Heartbeat interval (ms)
    "request_timeout": 10000,       # HTTP request timeout (ms)
    "ws_url": "wss://...",          # Custom WebSocket URL
    "logger": custom_logger,        # Custom logger instance
})
```

#### Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `connect_async()` | Establish WebSocket connection | `None` |
| `disconnect()` | Disconnect | `None` |
| `reply(frame, body, cmd?)` | Send reply message (generic) | `None` |
| `reply_stream(frame, stream_id, content, finish?, msg_item?, feedback?)` | Send streaming reply | `None` |
| `reply_welcome(frame, body)` | Send welcome reply (within 5s of event) | `None` |
| `reply_template_card(frame, template_card, feedback?)` | Reply with template card | `None` |
| `reply_stream_with_card(frame, stream_id, content, finish?, options?)` | Send stream + card combo | `None` |
| `update_template_card(frame, template_card, userids?)` | Update template card (within 5s) | `None` |
| `send_message(chatid, body)` | Proactively send message | `None` |
| `download_file(url, aes_key?)` | Download and optionally decrypt file | `tuple[bytes, str?]` |
| `upload_media(file_path)` | Upload media file (3-step WebSocket protocol) | `UploadResult` |
| `reply_media(frame, file_path)` | Upload file and reply with it as media | `WsFrame` |
| `send_media_message(chatid, file_path)` | Upload file and proactively send media to chat | `WsFrame` |

#### Events

| Event | Callback | Description |
|-------|----------|-------------|
| `connected` | `()` | WebSocket connected |
| `authenticated` | `()` | Authentication successful |
| `disconnected` | `(reason)` | Connection lost |
| `reconnecting` | `(attempt)` | Reconnecting (attempt N) |
| `error` | `(frame)` | Error occurred |
| `message` | `(frame)` | Any message received |
| `message.text` | `(frame)` | Text message |
| `message.image` | `(frame)` | Image message |
| `message.mixed` | `(frame)` | Mixed content message |
| `message.voice` | `(frame)` | Voice message |
| `message.file` | `(frame)` | File message |
| `event` | `(frame)` | Any event |
| `event.enter_chat` | `(frame)` | User entered chat |
| `event.template_card_event` | `(frame)` | Card button clicked |
| `event.feedback_event` | `(frame)` | User feedback |

## File Upload

Upload local media files (images, videos, voice, files) via the WebSocket 3-step protocol, then use the returned `media_id` to reply or send proactively:

```python
import asyncio
from wecom_aibot_sdk import WSClient

async def main():
    client = WSClient({
        "bot_id": "your-bot-id",
        "secret": "your-bot-secret",
    })

    # On text message, upload and reply with an image
    async def on_text(frame):
        result = await client.upload_media("/path/to/image.png")
        print(f"Upload success: media_id={result.media_id}, type={result.media_type}")

        # Reply as media message
        await client.reply_media(frame, "/path/to/image.png")

    client.on("message.text", on_text)

    # Proactively send a file to a user
    async def send_file():
        await client.send_media_message("userid", "/path/to/document.pdf")

    await client.connect_async()
    while client.is_connected:
        await asyncio.sleep(1)

asyncio.run(main())
```

**Notes:**
- Maximum single file size is **200MB**
- Media type is auto-detected from file extension: `image` / `video` / `voice` / `file`
- Upload uses chunked transfer (512KB per chunk) for stable large file uploads

## File Download

Download and decrypt files (images, documents) from messages:

```python
import asyncio
from wecom_aibot_sdk import WSClient

async def main():
    client = WSClient({
        "bot_id": "your-bot-id",
        "secret": "your-bot-secret",
    })

    # Handle file messages
    async def on_file(frame):
        file_info = frame.body.get("file", {})
        url = file_info.get("url", "")
        aes_key = file_info.get("aeskey", "")

        if url:
            # Download and decrypt (aes_key is optional)
            buffer, filename = await client.download_file(url, aes_key)
            print(f"Downloaded: {filename}, size: {len(buffer)} bytes")

    client.on("message.file", on_file)

    # Handle image messages similarly
    async def on_image(frame):
        image_info = frame.body.get("image", {})
        url = image_info.get("url", "")
        aes_key = image_info.get("aeskey", "")

        if url and aes_key:
            buffer, _ = await client.download_file(url, aes_key)
            # buffer contains decrypted image data

    client.on("message.image", on_image)

    await client.connect_async()
    while client.is_connected:
        await asyncio.sleep(1)

asyncio.run(main())
```

## Logging

The SDK uses Python's built-in `logging` module. Default log level is `WARNING`.

```python
import logging
from wecom_aibot_sdk import WSClient, WSClientOptions, DefaultLogger

# Create logger with custom level
logger = DefaultLogger(level=logging.DEBUG)

# Or change level at runtime
logger.set_level(logging.INFO)

# Pass to client
client = WSClient(WSClientOptions(
    bot_id="your-bot-id",
    secret="your-bot-secret",
    logger=logger,
))

# Available levels:
# logging.DEBUG    - All messages
# logging.INFO     - INFO + WARNING + ERROR
# logging.WARNING  - WARNING + ERROR (default)
# logging.ERROR    - ERROR only
```

You can also use your own logger by implementing the `Logger` protocol:

```python
class MyLogger:
    def debug(self, msg, *args): ...
    def info(self, msg, *args): ...
    def warn(self, msg, *args): ...
    def error(self, msg, *args): ...

client = WSClient({"bot_id": "...", "secret": "...", "logger": MyLogger()})
```

## Project Structure

```
wecom_aibot_sdk/
├── __init__.py          # Package entry, exports
├── client.py            # WSClient core client
├── ws.py                # WebSocket connection manager
├── message_handler.py   # Message parsing and event dispatch
├── api.py               # HTTP API client (file download)
├── upload.py            # Media file upload helpers (chunking, type detection)
├── crypto.py            # AES-256-CBC file decryption
├── logger.py            # Default logger implementation
├── utils.py             # Utility functions (generate_req_id, etc.)
└── types/               # Type definitions
    ├── __init__.py
    ├── config.py        # Configuration types
    ├── event.py         # Event types
    ├── message.py       # Message types
    ├── api.py           # API/WebSocket frame types
    └── common.py        # Common types (Logger)
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
ruff format .
```

## License

MIT
