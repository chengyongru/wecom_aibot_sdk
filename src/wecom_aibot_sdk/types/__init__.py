"""Type definitions for WeCom AI Bot SDK"""

from .config import WSClientOptions
from .event import EventType
from .message import (
    BaseMessage,
    EventMessage,
    MessageType,
    ReplyFeedback,
    ReplyMsgItem,
    TemplateCard,
    SendMarkdownMsgBody,
    SendTemplateCardMsgBody,
)
from .api import WsFrame, WsFrameHeaders, CmdType
from .common import Logger

__all__ = [
    "WSClientOptions",
    "EventType",
    "MessageType",
    "BaseMessage",
    "EventMessage",
    "ReplyFeedback",
    "ReplyMsgItem",
    "TemplateCard",
    "SendMarkdownMsgBody",
    "SendTemplateCardMsgBody",
    "WsFrame",
    "WsFrameHeaders",
    "CmdType",
    "Logger",
]
