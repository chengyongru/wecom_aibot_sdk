# WeCom AI Bot Python SDK

Enterprise WeChat AI Bot Python SDK - Based on WebSocket long connection, providing message sending/receiving, streaming replies, template cards, event callbacks, file download/decryption and other core capabilities.

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
- **File Download & Decryption** - Built-in AES-256-CBC file decryption, each image/file message has its own aeskey
- **Pluggable Logging** - Supports custom Logger, includes DefaultLogger with timestamps

## Installation

```bash
pip install wecom-aibot-sdk
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
| `download_file(url, aes_key)` | Download and decrypt file | `tuple[bytes, str?]` |

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

## Project Structure

```
wecom_aibot_sdk/
├── __init__.py          # Package entry, exports
├── client.py            # WSClient core client
├── ws.py                # WebSocket connection manager
├── message_handler.py   # Message parsing and event dispatch
├── api.py               # HTTP API client (file download)
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
