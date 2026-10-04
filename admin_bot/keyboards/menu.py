from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from admin_bot.keyboards.start import StartZone, menu_reply_kb, welcome_kb

MENU_BUTTON_KEY = "menu.btn_menu"


def full_menu_kb(*, is_super_admin: bool) -> InlineKeyboardMarkup:
    buttons: dict[StartZone, str] = {
        StartZone.CHANNELS: _("menu.btn_channels"),
    }
    if is_super_admin:
        buttons[StartZone.ADMINS] = _("menu.btn_admins")
    buttons[StartZone.LANGUAGE] = _("menu.btn_language")
    return welcome_kb(buttons=buttons)


def menu_button_markup() -> ReplyKeyboardMarkup:
    return menu_reply_kb(menu_text=_(MENU_BUTTON_KEY))
