from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from admin_bot.keyboards.start import BackCB


class ChannelDeleteConfirmCB(CallbackData, prefix="ch_del_ok"):
    chat_id: int


class ChannelAddCB(CallbackData, prefix="ch_add"):
    pass


class ChannelRefreshCB(CallbackData, prefix="ch_refresh"):
    pass


class ChannelJoinConfirmCB(CallbackData, prefix="ch_join"):
    pass


class ChannelCancelCB(CallbackData, prefix="ch_cancel"):
    pass


def channels_kb(
    *,
    add_text: str,
    refresh_text: str,
    back_text: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=add_text, callback_data=ChannelAddCB().pack())],
            [InlineKeyboardButton(text=refresh_text, callback_data=ChannelRefreshCB().pack())],
            [InlineKeyboardButton(text=back_text, callback_data=BackCB().pack())],
        ]
    )


def channel_confirm_kb(*, confirm_text: str, cancel_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=confirm_text, callback_data=ChannelJoinConfirmCB().pack())],
            [InlineKeyboardButton(text=cancel_text, callback_data=ChannelCancelCB().pack())],
        ]
    )


def channel_delete_confirm_kb(
    *,
    chat_id: int,
    yes_text: str,
    no_text: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=yes_text,
                    callback_data=ChannelDeleteConfirmCB(chat_id=chat_id).pack(),
                ),
                InlineKeyboardButton(text=no_text, callback_data=ChannelCancelCB().pack()),
            ],
        ]
    )


def channel_cancel_kb(*, cancel_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=cancel_text, callback_data=ChannelCancelCB().pack())],
        ]
    )
