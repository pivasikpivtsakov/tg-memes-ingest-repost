from collections.abc import Sequence

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from admin_bot.keyboards.start import BackCB


class AdminAddCB(CallbackData, prefix="adm_add"):
    pass


class AdminRemoveCB(CallbackData, prefix="adm_rm"):
    user_id: int


class AdminCancelCB(CallbackData, prefix="adm_cancel"):
    pass


def admins_kb(
    *,
    removable_ids: Sequence[int],
    add_text: str,
    remove_prefix: str,
    back_text: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=add_text, callback_data=AdminAddCB().pack())]
    ]
    for user_id in removable_ids:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{remove_prefix} {user_id}",
                    callback_data=AdminRemoveCB(user_id=user_id).pack(),
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=back_text, callback_data=BackCB().pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_cancel_kb(*, cancel_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=cancel_text, callback_data=AdminCancelCB().pack())],
        ]
    )
