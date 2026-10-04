from aiogram import Router
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import gettext as _

router = Router(name="fallback")


@router.callback_query()
async def fallback_callback(callback: CallbackQuery) -> None:
    await callback.answer()


@router.message()
async def fallback(message: Message) -> None:
    await message.answer(_("unknown"))
