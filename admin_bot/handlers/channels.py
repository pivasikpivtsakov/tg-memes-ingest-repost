import logging
import re
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

from admin_bot.forms.menu import (
    clear_extra_messages,
    remember_panel_messages,
    show_panel,
    show_panel_from_chat,
)
from admin_bot.forms.states import AddChannel
from admin_bot.keyboards.channels import (
    ChannelAddCB,
    ChannelCancelCB,
    ChannelDeleteConfirmCB,
    ChannelJoinConfirmCB,
    ChannelRefreshCB,
    channel_cancel_kb,
    channel_confirm_kb,
    channel_delete_confirm_kb,
    channels_kb,
)
from admin_bot.keyboards.start import OpenZoneCB, StartZone
from admin_bot.services.meme import is_from_our_public, is_our_public_chat, source_channel_from_message
from admin_bot.utils.telegram import ignore_message_gone, ignore_not_modified
from shared.redis import AllowedChatsRepository
from shared.services import (
    ChannelResult,
    ChannelTarget,
    ChannelTargetKind,
    join_and_allow,
    leave_and_unallow,
    parse_channel_target,
    refresh_allowed_chat_labels,
    resolve_channel,
)

logger = logging.getLogger(__name__)
router = Router(name="channels")

_JOIN_KIND = "join_kind"
_JOIN_VALUE = "join_value"
_TG_TEXT_LIMIT = 4096
_CHDEL_RE = re.compile(r"^/chdel_m(\d+)(?:@\w+)?$")


class IsAddChannelInput(BaseFilter):
    async def __call__(self, message: Message, config_target_chat_id: str) -> bool:
        if is_from_our_public(message, config_target_chat_id):
            return False
        if source_channel_from_message(message) is not None:
            return True
        text = message.text
        if text and text.startswith("/"):
            return False
        return bool(text)


class ChannelDeleteCommand(BaseFilter):
    async def __call__(self, message: Message) -> dict | bool:
        text = (message.text or "").strip()
        matched = _CHDEL_RE.fullmatch(text)
        if matched is None:
            return False
        return {"delete_chat_id": -int(matched.group(1))}


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


def _delete_command(chat_id: int) -> str:
    return f"/chdel_m{abs(chat_id)}"


def _channel_block(index: int, chat_id: int, label: str) -> str:
    return f"{index}. {escape(label)}\n{_delete_command(chat_id)}"


def _list_chunks(chats: dict[int, str]) -> list[str]:
    title = _("channels.title").format(count=len(chats))
    if not chats:
        return [f"{title}\n\n{_('channels.empty')}"]

    chunks: list[str] = []
    current = title
    for index, (chat_id, label) in enumerate(chats.items(), start=1):
        block = _channel_block(index, chat_id, label)
        if len(block) > _TG_TEXT_LIMIT:
            block = block[:_TG_TEXT_LIMIT]
        joined = f"{current}\n\n{block}" if current == title else f"{current}\n{block}"
        if len(joined) <= _TG_TEXT_LIMIT:
            current = joined
            continue
        if current:
            chunks.append(current)
        current = block
    if current:
        chunks.append(current)
    return chunks


def _channels_markup():
    return channels_kb(
        add_text=_("channels.btn_add"),
        refresh_text=_("channels.btn_refresh"),
        back_text=_("menu.btn_back"),
    )


async def _show_list(
    *,
    callback: CallbackQuery,
    state: FSMContext,
    allowed_chats: AllowedChatsRepository,
    answer: bool = True,
) -> None:
    await state.set_state(None)
    if not isinstance(callback.message, Message):
        if answer:
            await callback.answer()
        return
    chats = await allowed_chats.all()
    chunks = _list_chunks(chats)
    markup = _channels_markup()
    await clear_extra_messages(
        bot=callback.message.bot,
        chat_id=callback.message.chat.id,
        state=state,
    )
    first_markup = markup if len(chunks) == 1 else None
    with ignore_not_modified():
        await callback.message.edit_text(chunks[0], reply_markup=first_markup)
    extra_ids: list[int] = []
    menu_id = callback.message.message_id
    if len(chunks) > 1:
        extra_ids.append(menu_id)
        for index, chunk in enumerate(chunks[1:]):
            is_last = index == len(chunks) - 2
            sent = await callback.message.answer(
                chunk,
                reply_markup=markup if is_last else None,
            )
            if is_last:
                menu_id = sent.message_id
            else:
                extra_ids.append(sent.message_id)
    await remember_panel_messages(state=state, menu_id=menu_id, extra_ids=extra_ids)
    if answer:
        await callback.answer()


@router.message(ChannelDeleteCommand())
async def confirm_delete_from_command(
    message: Message,
    state: FSMContext,
    allowed_chats: AllowedChatsRepository,
    delete_chat_id: int,
) -> None:
    with ignore_message_gone():
        await message.delete()
    await state.set_state(None)
    chats = await allowed_chats.all()
    label = chats.get(delete_chat_id, str(delete_chat_id))
    await show_panel_from_chat(
        bot=message.bot,
        chat_id=message.chat.id,
        state=state,
        text=_("channels.remove_confirm").format(label=escape(label)),
        markup=channel_delete_confirm_kb(
            chat_id=delete_chat_id,
            yes_text=_("menu.btn_yes"),
            no_text=_("menu.btn_no"),
        ),
    )


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.CHANNELS))
async def open_channels(
    callback: CallbackQuery,
    state: FSMContext,
    allowed_chats: AllowedChatsRepository,
) -> None:
    await _show_list(callback=callback, state=state, allowed_chats=allowed_chats)


@router.callback_query(ChannelAddCB.filter())
async def start_add_channel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddChannel.awaiting_target)
    await show_panel(
        callback=callback,
        text=_("channels.add_prompt"),
        markup=channel_cancel_kb(cancel_text=_("menu.btn_cancel")),
        state=state,
    )


@router.callback_query(ChannelRefreshCB.filter())
async def refresh_channel_labels(
    callback: CallbackQuery,
    state: FSMContext,
    allowed_chats: AllowedChatsRepository,
    tg_client: TelegramClient,
) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await clear_extra_messages(
            bot=callback.message.bot,
            chat_id=callback.message.chat.id,
            state=state,
        )
        with ignore_not_modified():
            await callback.message.edit_text(_("channels.refreshing"), reply_markup=None)
        await remember_panel_messages(state=state, menu_id=callback.message.message_id)
    try:
        await refresh_allowed_chat_labels(tg_client, allowed_chats)
    except Exception as exc:
        logger.warning("Failed to refresh channel labels: %s", exc)
    await _show_list(
        callback=callback,
        state=state,
        allowed_chats=allowed_chats,
        answer=False,
    )


@router.callback_query(ChannelCancelCB.filter())
async def cancel_channel_flow(
    callback: CallbackQuery,
    state: FSMContext,
    allowed_chats: AllowedChatsRepository,
) -> None:
    await _show_list(callback=callback, state=state, allowed_chats=allowed_chats)


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
    await _show_list(
        callback=callback,
        state=state,
        allowed_chats=allowed_chats,
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
