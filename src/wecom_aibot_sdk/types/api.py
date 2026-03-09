"""API and WebSocket frame types"""

from dataclasses import dataclass, field
from typing import Any, Optional, TypedDict


class WsFrameHeaders(TypedDict):
    """WebSocket frame headers (minimal required)"""

    req_id: str


@dataclass
class WsFrame:
    """WebSocket frame structure"""

    headers: WsFrameHeaders
    cmd: Optional[str] = None
    body: Any = None
    errcode: Optional[int] = None
    errmsg: Optional[str] = None


# Command types
class CmdType(str):
    """WebSocket command types"""

    SUBSCRIBE = "aibot_subscribe"  # Auth
    CALLBACK = "aibot_msg_callback"  # Message callback
    EVENT_CALLBACK = "aibot_event_callback"  # Event callback
    RESPONSE = "aibot_respond_msg"  # Reply
    HEARTBEAT = "ping"
    REPLY = "reply"
    REPLY_STREAM = "reply_stream"
    REPLY_WELCOME = "reply_welcome"
    REPLY_TEMPLATE_CARD = "reply_template_card"
    UPDATE_TEMPLATE_CARD = "update_template_card"
    SEND_MESSAGE = "send_message"
