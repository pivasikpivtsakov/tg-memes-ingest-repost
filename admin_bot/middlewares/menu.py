from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject
from aiogram.utils.i18n import I18n

from admin_bot.forms.menu import MenuContext, open_menu
from admin_bot.i18n import LANGUAGE_NAMES
from admin_bot.keyboards.menu import MENU_BUTTON_KEY

_MENU_COMMAND = "/menu"


def _is_menu_command(text: str) -> bool:
    head = text.split(maxsplit=1)[0]
    return head.split("@", 1)[0] == _MENU_COMMAND


def _is_menu_trigger(message: Message, i18n: I18n) -> bool:
    text = message.text
    if text is None:
        return False
    if _is_menu_command(text):
        return True
    labels = {i18n.gettext(MENU_BUTTON_KEY, locale=locale) for locale in LANGUAGE_NAMES}
    return text in labels


class MenuMiddleware(BaseMiddleware):
    def __init__(self, *, i18n: I18n) -> None:
        self._i18n = i18n

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not _is_menu_trigger(event, self._i18n):
            return await handler(event, data)
        state: FSMContext = data["state"]
        await open_menu(
            MenuContext(
                target=event,
                state=state,
                is_super_admin=bool(data.get("is_super_admin")),
            )
        )
        return None
