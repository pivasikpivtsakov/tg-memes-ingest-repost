from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, User
from aiogram.utils.i18n import gettext as _

from shared.redis import AdminIdsRepository


class AccessMiddleware(BaseMiddleware):
    def __init__(self, *, admins: AdminIdsRepository) -> None:
        self._admins = admins

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is None:
            return None
        is_super_admin = await self._admins.is_super(user_id=user.id)
        if not is_super_admin and not await self._admins.contains(user_id=user.id):
            await _reject(event)
            return None
        data["is_super_admin"] = is_super_admin
        return await handler(event, data)


async def _reject(event: TelegramObject) -> None:
    text = _("access.denied")
    if not isinstance(event, Update):
        return
    if event.message is not None:
        await event.message.answer(text)
    elif event.callback_query is not None:
        await event.callback_query.answer(text, show_alert=True)
