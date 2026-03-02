from typing import Any, Awaitable, Callable, Dict
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
                user.id, chat_id, user.username, user.first_name
            )

        return await handler(event, data)
