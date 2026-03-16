from typing import Any, Awaitable, Callable, Dict
import sentry_sdk
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from app.db import repositories as repo


class RegisterMiddleware(BaseMiddleware):
    """Auto-register chat and user on every incoming update."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        chat_id = None
        user = None

        if isinstance(event, Message) and event.chat and event.from_user:
            chat_id = event.chat.id
            user = event.from_user
            chat_title = event.chat.title or event.chat.full_name
        elif isinstance(event, CallbackQuery) and event.message and event.from_user:
            chat_id = event.message.chat.id
            user = event.from_user
            chat_title = event.message.chat.title or event.message.chat.full_name
        else:
            return await handler(event, data)

        if chat_id and user:
            # Check if chat is banned
            if await repo.is_chat_banned(chat_id):
                return

            await repo.get_or_create_chat(chat_id, chat_title, user.id)
            await repo.get_or_create_user(
                user.id, chat_id, user.username, user.first_name,
                last_name=user.last_name,
                language_code=user.language_code,
                is_premium=bool(user.is_premium),
            )

            # Track message authorship + text for reaction attribution & quotes
            if isinstance(event, Message) and event.message_id:
                msg_text = event.text or event.caption or None
                media_type = None
                if event.photo:
                    media_type = "photo"
                elif event.voice:
                    media_type = "voice"
                elif event.video_note:
                    media_type = "video_note"
                elif event.video:
                    media_type = "video"
                elif event.sticker:
                    media_type = "sticker"
                elif event.audio:
                    media_type = "audio"
                elif event.document:
                    media_type = "document"
                await repo.save_message_author(
                    chat_id, event.message_id, user.id, msg_text, media_type,
                )

        return await handler(event, data)


class SentryContextMiddleware(BaseMiddleware):
    """Set Sentry user/chat context on every update."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = None
        chat = None

        if isinstance(event, Message):
            user = event.from_user
            chat = event.chat
        elif isinstance(event, CallbackQuery) and event.message:
            user = event.from_user
            chat = event.message.chat

        if user:
            sentry_sdk.set_user({"id": user.id, "username": user.username})
        if chat:
            sentry_sdk.set_tag("chat_id", chat.id)
            sentry_sdk.set_tag("chat_title", chat.title or chat.full_name)

        return await handler(event, data)
