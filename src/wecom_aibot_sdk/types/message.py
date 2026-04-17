"""Message types"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class MessageType(str, Enum):
    """Message type enumeration"""

    TEXT = "text"
    IMAGE = "image"
    MIXED = "mixed"
    VOICE = "voice"
    FILE = "file"


@dataclass
class QuoteContent:
    """Quoted message content"""

    msgid: str
    content: str


@dataclass
class MessageFrom:
    """Message sender info"""

    userid: str
    corpid: Optional[str] = None


@dataclass
class BaseMessage:
    """Base message structure"""

    msgid: str
    aibotid: str
    chattype: str  # 'single' | 'group'
    from_userid: str
    msgtype: str
    chatid: Optional[str] = None
    create_time: Optional[int] = None
    response_url: Optional[str] = None
    quote: Optional[QuoteContent] = None


@dataclass
class TextContent:
    """Text message content"""

    content: str


@dataclass
class ImageContent:
    """Image message content"""

    url: str
    aeskey: str


@dataclass
class VoiceContent:
    """Voice message content (transcribed to text)"""

    content: str


@dataclass
class FileContent:
    """File message content"""

    url: str
    aeskey: str
    name: Optional[str] = None
    size: Optional[int] = None


@dataclass
class MixedItem:
    """Mixed message item"""

    type: str  # 'text' | 'image'
    text: Optional[TextContent] = None
    image: Optional[ImageContent] = None


@dataclass
class EventContent:
    """Event content"""

    event_type: str
    task_id: Optional[str] = None
    card_id: Optional[str] = None
    response_code: Optional[str] = None
    feedback: Optional[str] = None


@dataclass
class EventMessage:
    """Event message structure"""

    msgid: str
    create_time: int
    aibotid: str
    msgtype: str  # always 'event'
    event: EventContent
    from_userid: str
    chattype: Optional[str] = None
    chatid: Optional[str] = None
    corpid: Optional[str] = None


# Template Card Types
@dataclass
class CardTitle:
    """Card title"""

    title: str
    desc: Optional[str] = None


@dataclass
class CardAction:
    """Card action"""

    type: str  # 'url' | 'task'
    url: Optional[str] = None
    taskid: Optional[str] = None


@dataclass
class CardButton:
    """Card button"""

    text: str
    key: str


@dataclass
class TemplateCard:
    """Template card content"""

    card_type: str
    main_title: Optional[CardTitle] = None
    sub_title: Optional[str] = None
    card_action: Optional[CardAction] = None
    button_list: list[CardButton] = field(default_factory=list)
    task_id: Optional[str] = None
    # Additional fields for different card types
    source: Optional[dict[str, Any]] = None
    card_image: Optional[dict[str, Any]] = None
    horizontal_content_list: Optional[list[dict[str, Any]]] = None
    jump_list: Optional[list[dict[str, Any]]] = None


@dataclass
class ReplyFeedback:
    """Reply feedback info"""

    msgid: Optional[str] = None
    is_denied: Optional[bool] = None


@dataclass
class ReplyMsgItem:
    """Reply message item for mixed content"""

    type: str  # 'text' | 'image'
    text: Optional[str] = None
    image_url: Optional[str] = None


@dataclass
class SendMarkdownMsgBody:
    """Send markdown message body"""

    msgtype: str = "markdown"
    markdown: dict[str, str] = field(default_factory=lambda: {"content": ""})


@dataclass
class SendTemplateCardMsgBody:
    """Send template card message body"""

    msgtype: str = "template_card"
    template_card: dict[str, Any] = field(default_factory=dict)


class MediaType(str, Enum):
    """WeCom media type enumeration"""

    IMAGE = "image"
    VIDEO = "video"
    VOICE = "voice"
    FILE = "file"


@dataclass
class UploadResult:
    """Result of a media upload operation"""

    media_id: str
    media_type: str
