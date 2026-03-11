# 企业微信智能机器人 Python SDK

[![PyPI version](https://img.shields.io/pypi/v/wecom-aibot-sdk-python)](https://pypi.org/project/wecom-aibot-sdk-python/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[English](./docs/README_en.md)

基于 WebSocket 长连接通道，提供消息收发、流式回复、模板卡片、事件回调、文件下载解密等核心能力。

## 安装

```bash
pip install wecom-aibot-sdk-python
```

## 功能特性

- **WebSocket 长连接** - 内置默认地址 `wss://openws.work.weixin.qq.com`，开箱即用
- **自动认证** - 连接后自动发送认证帧（botId + secret）
- **心跳保活** - 自动维护心跳，ACK 缺失时自动检测连接问题
- **自动重连** - 指数退避重连策略（1s → 2s → 4s → ... → 最大 30s）
- **消息分发** - 自动解析消息类型并触发相应事件（text/image/mixed/voice/file）
- **流式回复** - 内置流式回复方法，支持 Markdown 和混合内容
- **模板卡片** - 支持回复模板卡片消息、流式+卡片组合回复、卡片更新
- **主动推送** - 主动向指定会话发送 Markdown 或模板卡片消息
- **事件回调** - 支持 enter_chat、template_card_event、feedback_event
- **串行回复队列** - 相同 req_id 的回复串行发送，自动等待回执
- **文件下载解密** - 内置 AES-256-CBC 文件解密，支持 RFC 5987 文件名编码
- **可插拔日志** - 使用 Python 内置 `logging` 模块，默认 WARNING 级别


## 快速开始

```python
import asyncio
from wecom_aibot_sdk import WSClient, generate_req_id

async def main():
    # 1. 创建客户端实例
    client = WSClient({
        "bot_id": "your-bot-id",
        "secret": "your-bot-secret",
    })

    # 2. 监听文本消息并以流式方式回复
    async def on_text(frame):
        content = frame.body.get("text", {}).get("content", "")
        stream_id = generate_req_id("stream")

        # 发送中间内容
        await client.reply_stream(frame, stream_id, "正在思考...", finish=False)

        # 发送最终结果
        await client.reply_stream(frame, stream_id, f'你说："{content}"', finish=True)

    client.on("message.text", on_text)

    # 3. 监听进入会话事件（发送欢迎语）
    async def on_enter(frame):
        await client.reply_welcome(frame, {
            "msgtype": "text",
            "text": {"content": "你好！有什么可以帮助你的吗？"},
        })

    client.on("event.enter_chat", on_enter)

    # 4. 建立连接
    await client.connect_async()

    # 保持运行
    while client.is_connected:
        await asyncio.sleep(1)

asyncio.run(main())
```

## API 参考

### WSClient

核心客户端类，提供连接管理、消息收发。

```python
client = WSClient({
    "bot_id": "your-bot-id",
    "secret": "your-bot-secret",
    # 可选配置：
    "reconnect_interval": 1000,     # 重连基础延迟（毫秒）
    "max_reconnect_attempts": 10,   # 最大重连次数（-1 为无限）
    "heartbeat_interval": 30000,    # 心跳间隔（毫秒）
    "request_timeout": 10000,       # HTTP 请求超时（毫秒）
    "ws_url": "wss://...",          # 自定义 WebSocket URL
    "logger": custom_logger,        # 自定义日志实例
})
```

#### 方法

| 方法 | 描述 | 返回值 |
|------|------|--------|
| `connect_async()` | 建立 WebSocket 连接 | `None` |
| `disconnect()` | 断开连接 | `None` |
| `reply(frame, body, cmd?)` | 发送回复消息（通用） | `None` |
| `reply_stream(frame, stream_id, content, finish?, msg_item?, feedback?)` | 发送流式回复 | `None` |
| `reply_welcome(frame, body)` | 发送欢迎回复（事件后 5 秒内） | `None` |
| `reply_template_card(frame, template_card, feedback?)` | 回复模板卡片 | `None` |
| `reply_stream_with_card(frame, stream_id, content, finish?, options?)` | 发送流式 + 卡片组合 | `None` |
| `update_template_card(frame, template_card, userids?)` | 更新模板卡片（5 秒内） | `None` |
| `send_message(chatid, body)` | 主动发送消息 | `None` |
| `download_file(url, aes_key?)` | 下载并可选解密文件 | `tuple[bytes, str?]` |

#### 事件

| 事件 | 回调 | 描述 |
|------|------|------|
| `connected` | `()` | WebSocket 已连接 |
| `authenticated` | `()` | 认证成功 |
| `disconnected` | `(reason)` | 连接断开 |
| `reconnecting` | `(attempt)` | 正在重连（第 N 次） |
| `error` | `(frame)` | 发生错误 |
| `message` | `(frame)` | 收到任意消息 |
| `message.text` | `(frame)` | 文本消息 |
| `message.image` | `(frame)` | 图片消息 |
| `message.mixed` | `(frame)` | 混合内容消息 |
| `message.voice` | `(frame)` | 语音消息 |
| `message.file` | `(frame)` | 文件消息 |
| `event` | `(frame)` | 任意事件 |
| `event.enter_chat` | `(frame)` | 用户进入会话 |
| `event.template_card_event` | `(frame)` | 卡片按钮点击 |
| `event.feedback_event` | `(frame)` | 用户反馈 |

## 文件下载

下载并解密消息中的文件（图片、文档）：

```python
import asyncio
from wecom_aibot_sdk import WSClient

async def main():
    client = WSClient({
        "bot_id": "your-bot-id",
        "secret": "your-bot-secret",
    })

    # 处理文件消息
    async def on_file(frame):
        file_info = frame.body.get("file", {})
        url = file_info.get("url", "")
        aes_key = file_info.get("aeskey", "")

        if url:
            # 下载并解密（aes_key 可选）
            buffer, filename = await client.download_file(url, aes_key)
            print(f"已下载: {filename}, 大小: {len(buffer)} bytes")

    client.on("message.file", on_file)

    # 处理图片消息类似
    async def on_image(frame):
        image_info = frame.body.get("image", {})
        url = image_info.get("url", "")
        aes_key = image_info.get("aeskey", "")

        if url and aes_key:
            buffer, _ = await client.download_file(url, aes_key)
            # buffer 包含解密后的图片数据

    client.on("message.image", on_image)

    await client.connect_async()
    while client.is_connected:
        await asyncio.sleep(1)

asyncio.run(main())
```

## 日志配置

SDK 使用 Python 内置的 `logging` 模块，默认日志级别为 `WARNING`。

```python
import logging
from wecom_aibot_sdk import WSClient, WSClientOptions, DefaultLogger

# 创建指定级别的日志
logger = DefaultLogger(level=logging.DEBUG)

# 或运行时更改级别
logger.set_level(logging.INFO)

# 传入客户端
client = WSClient(WSClientOptions(
    bot_id="your-bot-id",
    secret="your-bot-secret",
    logger=logger,
))

# 可用级别：
# logging.DEBUG    - 所有日志
# logging.INFO     - INFO + WARNING + ERROR
# logging.WARNING  - WARNING + ERROR（默认）
# logging.ERROR    - 仅 ERROR
```

你也可以实现 `Logger` 协议使用自定义日志：

```python
class MyLogger:
    def debug(self, msg, *args): ...
    def info(self, msg, *args): ...
    def warn(self, msg, *args): ...
    def error(self, msg, *args): ...

client = WSClient({"bot_id": "...", "secret": "...", "logger": MyLogger()})
```

## 项目结构

```
wecom_aibot_sdk/
├── __init__.py          # 包入口，导出
├── client.py            # WSClient 核心客户端
├── ws.py                # WebSocket 连接管理器
├── message_handler.py   # 消息解析和事件分发
├── api.py               # HTTP API 客户端（文件下载）
├── crypto.py            # AES-256-CBC 文件解密
├── logger.py            # 默认日志实现
├── utils.py             # 工具函数（generate_req_id 等）
└── types/               # 类型定义
    ├── __init__.py
    ├── config.py        # 配置类型
    ├── event.py         # 事件类型
    ├── message.py       # 消息类型
    ├── api.py           # API/WebSocket 帧类型
    └── common.py        # 通用类型（Logger）
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 格式化代码
ruff format .
```

## 许可证

MIT
