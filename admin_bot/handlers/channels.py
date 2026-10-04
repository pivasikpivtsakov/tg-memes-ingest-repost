import logging
from html import escape

from aiogram import F, Router
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import gettext as _
from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    InviteRequestSentError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)

from admin_bot.constants import CHANNEL_PAGE_SIZE
from admin_bot.forms.menu import show_panel
from admin_bot.forms.states import AddChannel
from admin_bot.keyboards.channels import (
    ChannelAddCB,
    ChannelCancelCB,
    ChannelDeleteCB,
    ChannelDeleteConfirmCB,
    ChannelJoinConfirmCB,
    ChannelLabelCB,
    ChannelPageCB,
    channel_cancel_kb,
    channel_confirm_kb,
    channel_delete_confirm_kb,
    channels_kb,
)
from admin_bot.keyboards.start import OpenZoneCB, StartZone
from admin_bot.services.meme import is_from_our_public, is_our_public_chat, source_channel_from_message
from shared.services import (
    ChannelResult,
    ChannelTarget,
    ChannelTargetKind,
    join_and_allow,
    leave_and_unallow,
    parse_channel_target,
    resolve_channel,
)
from shared.redis import AllowedChatsRepository

logger = logging.getLogger(__name__)
router = Router(name="channels")

_JOIN_KIND = "join_kind"
_JOIN_VALUE = "join_value"
_LIST_OFFSET = "channels_offset"


class IsAddChannelInput(BaseFilter):
    async def __call__(self, message: Message, config_target_chat_id: str) -> bool:
        if is_from_our_public(message, config_target_chat_id):
            return False
        if source_channel_from_message(message) is not None:
            return True
        return bool(message.text)


def channel_error_text(exc: BaseException, *, fallback: str = "channels.join_failed") -> str:
    if isinstance(exc, FloodWaitError):
        return _("channels.error_flood").format(seconds=exc.seconds)
    if isinstance(exc, (UsernameNotOccupiedError, UsernameInvalidError)):
        return _("channels.error_not_found")
    if isinstance(exc, (InviteHashExpiredError, InviteHashInvalidError)):
        return _("channels.error_invite")
    if isinstance(exc, ChannelPrivateError):
        return _("channels.error_private")
    if isinstance(exc, InviteRequestSentError):
        return _("channels.error_request")
    return _(fallback)


def _sorted_items(chats: dict[int, str]) -> list[tuple[int, str]]:
    return sorted(chats.items(), key=lambda item: item[1].lower())


def _list_view(*, chats: dict[int, str], offset: int):
    items = _sorted_items(chats)
    if offset >= len(items) and offset > 0:
        offset = max(0, ((len(items) - 1) // CHANNEL_PAGE_SIZE) * CHANNEL_PAGE_SIZE)
    page = items[offset:offset + CHANNEL_PAGE_SIZE]
    if not items:
        text = f"{_('channels.title')}\n\n{_('channels.empty')}"
    else:
        lines = [
            f"{idx}. {escape(label)}\n<code>{chat_id}</code>"
            for idx, (chat_id, label) in enumerate(page, start=offset + 1)
        ]
        text = f"{_('channels.title')}\n\n" + "\n".join(lines)
    markup = channels_kb(
        items=page,
        offset=offset,
        page_size=CHANNEL_PAGE_SIZE,
        total=len(items),
        add_text=_("channels.btn_add"),
        delete_text=_("channels.btn_delete"),
        prev_text=_("menu.btn_prev"),
        next_text=_("menu.btn_next"),
        back_text=_("menu.btn_back"),
    )
    return text, markup, offset


async def _show_list(
    *,
    callback: CallbackQuery,
    state: FSMContext,
    allowed_chats: AllowedChatsRepository,
    offset: int = 0,
    answer: bool = True,
) -> None:
    await state.set_state(None)
    chats = await allowed_chats.all()
    text, markup, offset = _list_view(chats=chats, offset=offset)
    await state.update_data({_LIST_OFFSET: offset})
    await show_panel(callback=callback, text=text, markup=markup, state=state, answer=answer)


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.CHANNELS))
async def open_channels(
    callback: CallbackQuery,
    state: FSMContext,
    allowed_chats: AllowedChatsRepository,
) -> None:
    await _show_list(callback=callback, state=state, allowed_chats=allowed_chats)


@router.callback_query(ChannelLabelCB.filter())
async def ignore_channel_label(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(ChannelPageCB.filter())
async def paginate_channels(
    callback: CallbackQuery,
    callback_data: ChannelPageCB,
    state: FSMContext,
    allowed_chats: AllowedChatsRepository,
) -> None:
    await _show_list(
        callback=callback,
        state=state,
        allowed_chats=allowed_chats,
        offset=callback_data.offset,
    )


@router.callback_query(ChannelAddCB.filter())
async def start_add_channel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddChannel.awaiting_target)
    await show_panel(
        callback=callback,
        text=_("channels.add_prompt"),
        markup=channel_cancel_kb(cancel_text=_("menu.btn_cancel")),
        state=state,
    )


@router.callback_query(ChannelCancelCB.filter())
async def cancel_channel_flow(
    callback: CallbackQuery,
    state: FSMContext,
    allowed_chats: AllowedChatsRepository,
) -> None:
    data = await state.get_data()
    await _show_list(
        callback=callback,
        state=state,
        allowed_chats=allowed_chats,
        offset=int(data.get(_LIST_OFFSET) or 0),
    )


@router.callback_query(ChannelDeleteCB.filter())
async def confirm_delete_channel(
    callback: CallbackQuery,
    callback_data: ChannelDeleteCB,
    state: FSMContext,
    allowed_chats: AllowedChatsRepository,
) -> None:
    chats = await allowed_chats.all()
    label = chats.get(callback_data.chat_id, str(callback_data.chat_id))
    await show_panel(
        callback=callback,
        text=_("channels.remove_confirm").format(label=escape(label)),
        markup=channel_delete_confirm_kb(
            chat_id=callback_data.chat_id,
            yes_text=_("menu.btn_yes"),
            no_text=_("menu.btn_no"),
        ),
        state=state,
    )


@router.callback_query(ChannelDeleteConfirmCB.filter())
async def delete_channel(
    callback: CallbackQuery,
    callback_data: ChannelDeleteConfirmCB,
    state: FSMContext,
    allowed_chats: AllowedChatsRepository,
    tg_client: TelegramClient,
) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(_("channels.removing"), reply_markup=None)
    try:
        await leave_and_unallow(tg_client, allowed_chats, callback_data.chat_id)
    except Exception as exc:
        logger.warning("Failed to leave channel %s: %s", callback_data.chat_id, exc)
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                channel_error_text(exc, fallback="channels.remove_failed"),
            )
        return
    data = await state.get_data()
    await _show_list(
        callback=callback,
        state=state,
        allowed_chats=allowed_chats,
        offset=int(data.get(_LIST_OFFSET) or 0),
        answer=False,
    )


@router.callback_query(ChannelJoinConfirmCB.filter(), AddChannel.confirming)
async def confirm_join(
    callback: CallbackQuery,
    state: FSMContext,
    allowed_chats: AllowedChatsRepository,
    tg_client: TelegramClient,
) -> None:
    data = await state.get_data()
    kind = data.get(_JOIN_KIND)
    value = data.get(_JOIN_VALUE)
    if not kind or not value:
        await callback.answer()
        return
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(_("channels.joining"), reply_markup=None)
    try:
        await join_and_allow(
            tg_client,
            allowed_chats,
            ChannelTarget(kind=ChannelTargetKind(kind), value=value),
        )
    except Exception as exc:
        logger.warning("Failed to join channel %s:%s: %s", kind, value, exc)
        if isinstance(callback.message, Message):
            await callback.message.edit_text(channel_error_text(exc))
        return
    await _show_list(
        callback=callback,
        state=state,
        allowed_chats=allowed_chats,
        answer=False,
    )


@router.message(AddChannel.awaiting_target, IsAddChannelInput())
async def receive_channel_target(
    message: Message,
    state: FSMContext,
    tg_client: TelegramClient,
    config_target_chat_id: str,
) -> None:
    target = _target_from_message(message, config_target_chat_id)
    if target is None:
        await message.answer(_("channels.invalid_target"))
        return
    await _send_preview(message=message, state=state, tg_client=tg_client, target=target)


def _target_from_message(message: Message, config_target_chat_id: str) -> ChannelTarget | None:
    source = source_channel_from_message(message)
    if source is not None:
        chat_id, username = source
        if is_our_public_chat(chat_id, username, config_target_chat_id):
            return None
        if username:
            return ChannelTarget(ChannelTargetKind.USERNAME, username)
        return ChannelTarget(ChannelTargetKind.ID, str(chat_id))
    if message.text:
        return parse_channel_target(message.text)
    return None


async def _send_preview(
    *,
    message: Message,
    state: FSMContext,
    tg_client: TelegramClient,
    target: ChannelTarget,
) -> None:
    try:
        result = await resolve_channel(tg_client, target)
    except Exception as exc:
        logger.warning("Failed to resolve channel %s: %s", target, exc)
        await message.answer(channel_error_text(exc))
        return
    await state.set_state(AddChannel.confirming)
    await state.update_data({_JOIN_KIND: target.kind.value, _JOIN_VALUE: target.value})
    await message.answer(
        _preview_text(result),
        reply_markup=channel_confirm_kb(
            confirm_text=_("menu.btn_confirm"),
            cancel_text=_("menu.btn_cancel"),
        ),
    )


def _preview_text(result: ChannelResult) -> str:
    if result.chat_id is None:
        return _("channels.preview_invite").format(title=escape(result.title or result.label or ""))
    username = f"@{result.username}" if result.username else _("common.dash")
    return _("channels.preview").format(
        title=escape(result.title or ""),
        username=escape(username),
        chat_id=result.chat_id,
    )
