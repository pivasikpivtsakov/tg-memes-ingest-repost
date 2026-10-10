from dataclasses import dataclass

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import gettext as _

from admin_bot.keyboards.menu import full_menu_kb, menu_button_markup
from admin_bot.utils.telegram import ignore_message_gone, ignore_not_modified

_MENU_MESSAGE_ID_KEY = "menu_message_id"
_EXTRA_MESSAGE_IDS_KEY = "panel_extra_ids"


@dataclass(frozen=True, slots=True)
class MenuContext:
    target: Message | CallbackQuery
    state: FSMContext
    is_super_admin: bool = False


async def remember_menu_message(*, state: FSMContext, message_id: int) -> None:
    await state.update_data({_MENU_MESSAGE_ID_KEY: message_id})


async def remember_panel_messages(
    *,
    state: FSMContext,
    menu_id: int,
    extra_ids: list[int] | None = None,
) -> None:
    await state.update_data(
        {
            _MENU_MESSAGE_ID_KEY: menu_id,
            _EXTRA_MESSAGE_IDS_KEY: list(extra_ids or []),
        }
    )


async def clear_extra_messages(*, bot, chat_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    extra_ids = data.get(_EXTRA_MESSAGE_IDS_KEY) or []
    for message_id in extra_ids:
        with ignore_message_gone():
            await bot.delete_message(chat_id=chat_id, message_id=int(message_id))
    if extra_ids:
        await state.update_data({_EXTRA_MESSAGE_IDS_KEY: []})


async def _delete_remembered_menu(*, bot, chat_id: int, state: FSMContext) -> None:
    await clear_extra_messages(bot=bot, chat_id=chat_id, state=state)
    data = await state.get_data()
    message_id = data.get(_MENU_MESSAGE_ID_KEY)
    if message_id is None:
        return
    with ignore_message_gone():
        await bot.delete_message(chat_id=chat_id, message_id=message_id)


async def render_menu(context: MenuContext) -> None:
    text = _("menu.welcome")
    markup = full_menu_kb(is_super_admin=context.is_super_admin)
    target = context.target
    if isinstance(target, CallbackQuery):
        if isinstance(target.message, Message):
            with ignore_not_modified():
                await target.message.edit_text(text, reply_markup=markup)
            await remember_menu_message(state=context.state, message_id=target.message.message_id)
        return
    sent = await target.answer(text, reply_markup=markup)
    await remember_menu_message(state=context.state, message_id=sent.message_id)


async def open_menu(context: MenuContext) -> None:
    target = context.target
    if isinstance(target, Message):
        await _delete_remembered_menu(
            bot=target.bot,
            chat_id=target.chat.id,
            state=context.state,
        )
    elif isinstance(target, CallbackQuery) and isinstance(target.message, Message):
        await clear_extra_messages(
            bot=target.message.bot,
            chat_id=target.message.chat.id,
            state=context.state,
        )
    await context.state.set_state(None)
    await render_menu(context)


async def show_panel(
    *,
    callback: CallbackQuery,
    text: str,
    markup,
    state: FSMContext | None = None,
    answer: bool = True,
) -> None:
    if not isinstance(callback.message, Message):
        if answer:
            await callback.answer()
        return
    if state is not None:
        await clear_extra_messages(
            bot=callback.message.bot,
            chat_id=callback.message.chat.id,
            state=state,
        )
    with ignore_not_modified():
        await callback.message.edit_text(text, reply_markup=markup)
    if state is not None:
        await remember_menu_message(state=state, message_id=callback.message.message_id)
    if answer:
        await callback.answer()


async def show_panel_from_chat(
    *,
    bot,
    chat_id: int,
    state: FSMContext,
    text: str,
    markup,
) -> None:
    await clear_extra_messages(bot=bot, chat_id=chat_id, state=state)
    data = await state.get_data()
    panel_id = data.get(_MENU_MESSAGE_ID_KEY)
    if panel_id is not None:
        try:
            await bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=int(panel_id),
                reply_markup=markup,
            )
            return
        except TelegramBadRequest as error:
            lowered = error.message.lower()
            if "message is not modified" in lowered:
                return
            if "message to edit not found" not in lowered:
                raise
    sent = await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    await remember_menu_message(state=state, message_id=sent.message_id)


async def install_menu_button(*, message: Message) -> None:
    await message.answer(_("menu.tap_menu"), reply_markup=menu_button_markup())
