from collections.abc import Sequence

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from admin_bot.keyboards.start import BackCB


class ChannelPageCB(CallbackData, prefix="ch_page"):
    offset: int


class ChannelDeleteCB(CallbackData, prefix="ch_del"):
    chat_id: int


class ChannelDeleteConfirmCB(CallbackData, prefix="ch_del_ok"):
    chat_id: int


class ChannelAddCB(CallbackData, prefix="ch_add"):
    pass


class ChannelLabelCB(CallbackData, prefix="ch_name"):
    pass


class ChannelJoinConfirmCB(CallbackData, prefix="ch_join"):
    pass


class ChannelCancelCB(CallbackData, prefix="ch_cancel"):
    pass


def _short(label: str) -> str:
    if len(label) <= 40:
        return label
    return f"{label[:37]}..."


def channels_kb(
    *,
    items: Sequence[tuple[int, str]],
    offset: int,
    page_size: int,
    total: int,
    add_text: str,
    delete_text: str,
    prev_text: str,
    next_text: str,
    back_text: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for chat_id, label in items:
        rows.append(
            [
                InlineKeyboardButton(text=_short(label), callback_data=ChannelLabelCB().pack()),
                InlineKeyboardButton(
                    text=delete_text,
                    callback_data=ChannelDeleteCB(chat_id=chat_id).pack(),
                ),
            ]
        )

    nav: list[InlineKeyboardButton] = []
    if offset > 0:
        nav.append(
            InlineKeyboardButton(
                text=prev_text,
                callback_data=ChannelPageCB(offset=max(offset - page_size, 0)).pack(),
            )
        )
    if offset + page_size < total:
        nav.append(
            InlineKeyboardButton(
                text=next_text,
                callback_data=ChannelPageCB(offset=offset + page_size).pack(),
            )
        )
    if nav:
        rows.append(nav)

    rows.append(
        [InlineKeyboardButton(text=add_text, callback_data=ChannelAddCB().pack())]
    )
    rows.append(
        [InlineKeyboardButton(text=back_text, callback_data=BackCB().pack())]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
