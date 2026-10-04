from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from admin_bot.forms.menu import MenuContext, install_menu_button, open_menu, render_menu
from admin_bot.keyboards.start import BackCB

router = Router(name="start")


def _menu_context(target: Message | CallbackQuery, state: FSMContext, is_super_admin: bool) -> MenuContext:
    return MenuContext(target=target, state=state, is_super_admin=is_super_admin)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    is_super_admin: bool,
) -> None:
    await state.set_state(None)
    await install_menu_button(message=message)
    await render_menu(_menu_context(message, state, is_super_admin))


@router.callback_query(BackCB.filter())
async def go_back(
    callback: CallbackQuery,
    state: FSMContext,
    is_super_admin: bool,
) -> None:
    await open_menu(_menu_context(callback, state, is_super_admin))
    await callback.answer()
