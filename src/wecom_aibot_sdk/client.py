"""
WeCom AI Bot WebSocket Client

Core client class providing connection management, message sending/receiving,
streaming replies, template cards, and file download/decryption.
"""

import asyncio
from typing import Any, Optional, Union

from .types import (
    WsFrame,
    WsFrameHeaders,
    WSClientOptions,
    MessageType,
    EventType,
    TemplateCard,
    ReplyFeedback,
    ReplyMsgItem,
    SendMarkdownMsgBody,
    SendTemplateCardMsgBody,
)
from .types.config import WSClientOptions as ConfigOptions
from .types.message import CardTitle, CardAction, CardButton
from .ws import WebSocketManager
from .message_handler import MessageHandler, EventHandler
from .api import WeComApiClient
from .logger import Logger, DefaultLogger
from .utils import generate_req_id


class WSClient:
    """
    WeCom AI Bot WebSocket Client

    Inherits event handling capabilities. Provides connection management,
    message sending/receiving, streaming replies, template cards, etc.
    """

    def __init__(self, options: WSClientOptions):
        """
        Initialize WebSocket client

        Args:
            options: Client configuration options
        """
        # Convert dict to dataclass if needed
        if isinstance(options, dict):
            options = ConfigOptions(**options)

        self._options = options
        self._logger = options.logger or DefaultLogger()
        self._message_handler = MessageHandler(self._logger)
        self._ws_manager = WebSocketManager(
            options=options,
            message_handler=self._message_handler,
            logger=self._logger,
        )
        self._api_client = WeComApiClient(options=options, logger=self._logger)

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected"""
        return self._ws_manager.is_connected

    @property
    def is_authenticated(self) -> bool:
        """Check if WebSocket is authenticated"""
        return self._ws_manager._authenticated

    @property
    def api(self) -> WeComApiClient:
        """Get internal API client instance"""
        return self._api_client

    def connect(self) -> "WSClient":
        """
        Establish WebSocket connection (async, returns self for chaining)

        Note: This returns self for chaining but connection is async.
        Use await connect_async() or run in event loop.
        """
        asyncio.create_task(self._ws_manager.connect())
        return self

    async def connect_async(self) -> None:
        """Establish WebSocket connection (async version)"""
        await self._ws_manager.connect()

    async def disconnect(self) -> None:
        """Disconnect WebSocket"""
        await self._ws_manager.disconnect()
        await self._api_client.close()

    def on(self, event: str, handler: EventHandler) -> None:
        """
        Register event handler

        Args:
            event: Event name (e.g., 'message.text', 'event.enter_chat')
            handler: Async callback function
        """
        self._message_handler.on(event, handler)

    def off(self, event: str, handler: Optional[EventHandler] = None) -> None:
        """
        Remove event handler

        Args:
            event: Event name
            handler: Specific handler to remove, or None to remove all
        """
        self._message_handler.off(event, handler)

    async def reply(
        self,
        frame: Union[WsFrame, WsFrameHeaders],
        body: dict[str, Any],
        cmd: str = "aibot_respond_msg",
    ) -> WsFrame:
        """
        Send reply message through WebSocket (generic method)

        Args:
            frame: Original frame (for req_id), can be WsFrame or just headers
            body: Message body
            cmd: Command type

        Returns:
            WsFrame: The ack frame from server
        """
        if isinstance(frame, dict):
            headers = frame
        else:
            headers = frame.headers

        ws_frame = WsFrame(headers=headers)
        return await self._ws_manager.send(ws_frame, body, cmd)

    async def reply_stream(
        self,
        frame: Union[WsFrame, WsFrameHeaders],
        stream_id: str,
        content: str,
        finish: bool = False,
        msg_item: Optional[list[ReplyMsgItem]] = None,
        feedback: Optional[ReplyFeedback] = None,
    ) -> WsFrame:
        """
        Send streaming text reply (supports Markdown)

        Args:
            frame: Original frame (for req_id)
            stream_id: Stream message ID (use generate_req_id('stream'))
            content: Reply content (supports Markdown)
            finish: Whether to end stream, default False
            msg_item: Mixed content items (only valid when finish=True)
            feedback: Feedback info (only set on first reply)

        Returns:
            WsFrame: The ack frame from server
        """
        if isinstance(frame, dict):
            headers = frame
        else:
            headers = frame.headers

        body: dict[str, Any] = {
            "msgtype": "stream",
            "stream": {
                "id": stream_id,
                "content": content,
                "finish": finish,
            },
        }

        if msg_item and finish:
            items = []
            for item in msg_item:
                item_data: dict[str, Any] = {"type": item.type}
                if item.type == "text" and item.text:
                    item_data["text"] = {"content": item.text}
                elif item.type == "image" and item.image_url:
                    item_data["image"] = {"url": item.image_url}
                items.append(item_data)
            body["stream"]["msg_item"] = items

        if feedback:
            feedback_data: dict[str, Any] = {}
            if feedback.msgid:
                feedback_data["msgid"] = feedback.msgid
            if feedback.is_denied is not None:
                feedback_data["is_denied"] = feedback.is_denied
            if feedback_data:
                body["stream"]["feedback"] = feedback_data

        ws_frame = WsFrame(headers=headers)
        return await self._ws_manager.send(ws_frame, body, "aibot_respond_msg")

    async def reply_welcome(
        self,
        frame: Union[WsFrame, WsFrameHeaders],
        body: dict[str, Any],
    ) -> WsFrame:
        """
        Send welcome reply (must be called within 5s of receiving enter_chat event)

        Args:
            frame: Original frame
            body: Message body (text or template_card)

        Returns:
            WsFrame: The ack frame from server
        """
        if isinstance(frame, dict):
            headers = frame
        else:
            headers = frame.headers

        ws_frame = WsFrame(headers=headers)
        return await self._ws_manager.send(ws_frame, body, "aibot_respond_welcome_msg")

    async def reply_template_card(
        self,
        frame: Union[WsFrame, WsFrameHeaders],
        template_card: TemplateCard,
        feedback: Optional[ReplyFeedback] = None,
    ) -> WsFrame:
        """
        Reply with template card message

        Args:
            frame: Original frame
            template_card: Template card content
            feedback: Feedback info (optional)

        Returns:
            WsFrame: The ack frame from server
        """
        if isinstance(frame, dict):
            headers = frame
        else:
            headers = frame.headers

        body: dict[str, Any] = {
            "msgtype": "template_card",
            "template_card": self._build_template_card(template_card),
        }

        if feedback:
            feedback_data: dict[str, Any] = {}
            if feedback.msgid:
                feedback_data["msgid"] = feedback.msgid
            if feedback.is_denied is not None:
                feedback_data["is_denied"] = feedback.is_denied
            if feedback_data:
                body["feedback"] = feedback_data

        ws_frame = WsFrame(headers=headers)
        return await self._ws_manager.send(ws_frame, body, "aibot_respond_msg")

    async def reply_stream_with_card(
        self,
        frame: Union[WsFrame, WsFrameHeaders],
        stream_id: str,
        content: str,
        finish: bool = False,
        options: Optional[dict[str, Any]] = None,
    ) -> WsFrame:
        """
        Send streaming message + template card combined reply

        Args:
            frame: Original frame
            stream_id: Stream message ID
            content: Reply content (supports Markdown)
            finish: Whether to end stream
            options: Additional options including:
                - msg_item: Mixed content items
                - stream_feedback: Stream message feedback
                - template_card: Template card content
                - card_feedback: Card feedback info

        Returns:
            WsFrame: The ack frame from server
        """
        if isinstance(frame, dict):
            headers = frame
        else:
            headers = frame.headers

        options = options or {}
        body: dict[str, Any] = {
            "msgtype": "stream_text_with_card",
            "stream_text": {
                "content": content,
                "finish": finish,
                "stream_id": stream_id,
            },
        }

        if options.get("msg_item") and finish:
            body["stream_text"]["msg_item"] = options["msg_item"]

        if options.get("stream_feedback"):
            body["stream_text"]["feedback"] = options["stream_feedback"]

        if options.get("template_card"):
            template_card = options["template_card"]
            if isinstance(template_card, TemplateCard):
                body["template_card"] = self._build_template_card(template_card)
            else:
                body["template_card"] = template_card

        if options.get("card_feedback"):
            body["card_feedback"] = options["card_feedback"]

        ws_frame = WsFrame(headers=headers)
        return await self._ws_manager.send(ws_frame, body, "aibot_respond_msg")

    async def update_template_card(
        self,
        frame: Union[WsFrame, WsFrameHeaders],
        template_card: TemplateCard,
        userids: Optional[list[str]] = None,
    ) -> WsFrame:
        """
        Update template card (response to template_card_event, must be called within 5s)

        Args:
            frame: Event frame (must contain event's req_id)
            template_card: Template card content (task_id must match callback's task_id)
            userids: User IDs to replace card for, empty means all users

        Returns:
            WsFrame: The ack frame from server
        """
        if isinstance(frame, dict):
            headers = frame
        else:
            headers = frame.headers

        body: dict[str, Any] = {
            "response_type": "update_template_card",
            "template_card": self._build_template_card(template_card),
        }

        if userids:
            body["userids"] = userids

        ws_frame = WsFrame(headers=headers)
        return await self._ws_manager.send(ws_frame, body, "aibot_respond_update_msg")

    async def send_message(
        self,
        chatid: str,
        body: Union[SendMarkdownMsgBody, SendTemplateCardMsgBody, dict[str, Any]],
    ) -> WsFrame:
        """
        Proactively send message (no callback frame needed)

        Args:
            chatid: Chat ID (user's userid for single chat, chatid for group)
            body: Message body (markdown or template_card)

        Returns:
            WsFrame: The ack frame from server
        """
        if isinstance(body, SendMarkdownMsgBody):
            msg_body = {
                "msgtype": "markdown",
                "markdown": body.markdown,
            }
        elif isinstance(body, SendTemplateCardMsgBody):
            msg_body = {
                "msgtype": "template_card",
                "template_card": body.template_card,
            }
        else:
            msg_body = body

        req_id = generate_req_id("aibot_send_msg")
        return await self._ws_manager.send_reply(
            req_id,
            {"chatid": chatid, **msg_body},
            "aibot_send_msg",
        )

    async def download_file(
        self,
        url: str,
        aes_key: Optional[str] = None,
    ) -> tuple[bytes, Optional[str]]:
        """
        Download and optionally decrypt file using AES key

        Args:
            url: File URL
            aes_key: AES key from message body (image.aeskey or file.aeskey).
                     If not provided, returns raw encrypted data.

        Returns:
            Tuple of (buffer, filename)
        """
        return await self._api_client.download_file(url, aes_key)

    def _build_template_card(self, card: TemplateCard) -> dict[str, Any]:
        """Build template card dict from TemplateCard object"""
        result: dict[str, Any] = {"card_type": card.card_type}

        if card.main_title:
            result["main_title"] = {
                "title": card.main_title.title,
            }
            if card.main_title.desc:
                result["main_title"]["desc"] = card.main_title.desc

        if card.sub_title:
            result["sub_title"] = card.sub_title

        if card.card_action:
            result["card_action"] = {"type": card.card_action.type}
            if card.card_action.url:
                result["card_action"]["url"] = card.card_action.url
            if card.card_action.taskid:
                result["card_action"]["taskid"] = card.card_action.taskid

        if card.button_list:
            result["button_list"] = [
                {"text": btn.text, "key": btn.key}
                for btn in card.button_list
            ]

        if card.task_id:
            result["task_id"] = card.task_id

        if card.source:
            result["source"] = card.source

        if card.card_image:
            result["card_image"] = card.card_image

        if card.horizontal_content_list:
            result["horizontal_content_list"] = card.horizontal_content_list

        if card.jump_list:
            result["jump_list"] = card.jump_list

        return result
