"""Configuration types"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..logger import Logger


@dataclass
class WSClientOptions:
    """WebSocket client configuration options"""

    bot_id: str
    secret: str
    reconnect_interval: int = 1000  # ms, exponential backoff: 1s -> 2s -> 4s -> ... -> 30s max
    max_reconnect_attempts: int = 10  # -1 for infinite
    heartbeat_interval: int = 30000  # ms
    request_timeout: int = 10000  # ms
    ws_url: str = "wss://openws.work.weixin.qq.com"
    logger: "Logger | None" = None
