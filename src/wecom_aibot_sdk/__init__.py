"""
WeCom AI Bot Python SDK
Based on WebSocket long connection, provides core capabilities including message sending/receiving, streaming replies, template cards, event callbacks, and file download decryption.
"""

from .client import WSClient
from .types import (
    WsFrame,
    WSClientOptions,
    MessageType,
    EventType,
    Logger,
    BaseMessage,
    EventMessage,
    TemplateCard,
    ReplyFeedback,
    ReplyMsgItem,
    MediaType,
    UploadResult,
)
from .utils import generate_req_id
from .logger import DefaultLogger

__all__ = [
    "WSClient",
    "WsFrame",
    "WSClientOptions",
    "MessageType",
    "EventType",
    "Logger",
    "BaseMessage",
    "EventMessage",
    "TemplateCard",
    "ReplyFeedback",
    "ReplyMsgItem",
    "MediaType",
    "UploadResult",
    "generate_req_id",
    "DefaultLogger",
]

__version__ = "0.1.6"
