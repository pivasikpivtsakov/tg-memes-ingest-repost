from collections.abc import Mapping

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from admin_bot.keyboards.start import BackCB


class SetLanguageCB(CallbackData, prefix="lang"):
    value: str


def language_kb(*, names: Mapping[str, str], back_text: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=label,
                callback_data=SetLanguageCB(value=code).pack(),
            )
        ]
        for code, label in names.items()
    ]
    rows.append([InlineKeyboardButton(text=back_text, callback_data=BackCB().pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)
