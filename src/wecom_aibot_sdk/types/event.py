"""Event types"""

from enum import Enum


class EventType(str, Enum):
    """Event type enumeration"""

    ENTER_CHAT = "enter_chat"
    TEMPLATE_CARD_EVENT = "template_card_event"
    FEEDBACK_EVENT = "feedback_event"
