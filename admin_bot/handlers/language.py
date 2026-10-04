from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import FSMI18nMiddleware
from aiogram.utils.i18n import gettext as _

from admin_bot.forms.menu import MenuContext, install_menu_button, open_menu, show_panel
from admin_bot.i18n import LANGUAGE_NAMES
from admin_bot.keyboards.language import SetLanguageCB, language_kb
from admin_bot.keyboards.start import OpenZoneCB, StartZone

router = Router(name="language")


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.LANGUAGE))
async def open_language(callback: CallbackQuery, state: FSMContext) -> None:
    await show_panel(
        callback=callback,
        text=_("language.title"),
        markup=language_kb(names=LANGUAGE_NAMES, back_text=_("menu.btn_back")),
        state=state,
    )


@router.callback_query(SetLanguageCB.filter())
async def set_language(
    callback: CallbackQuery,
    callback_data: SetLanguageCB,
    state: FSMContext,
    i18n_middleware: FSMI18nMiddleware,
    is_super_admin: bool,
) -> None:
    await i18n_middleware.set_locale(state=state, locale=callback_data.value)
    if isinstance(callback.message, Message):
        await install_menu_button(message=callback.message)
    await callback.answer(_("language.changed"))
    await open_menu(
        MenuContext(target=callback, state=state, is_super_admin=is_super_admin)
    )
