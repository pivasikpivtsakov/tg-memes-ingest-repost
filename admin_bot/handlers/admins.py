from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import gettext as _

from admin_bot.filters import IsSuperAdmin
from admin_bot.forms.menu import show_panel
from admin_bot.forms.states import ManageAdmins
from admin_bot.keyboards.admins import (
    AdminAddCB,
    AdminCancelCB,
    AdminRemoveCB,
    admin_cancel_kb,
    admins_kb,
)
from admin_bot.keyboards.start import OpenZoneCB, StartZone
from shared.redis import AdminIdsRepository

router = Router(name="admins")

_is_super_admin = IsSuperAdmin()


def _panel_view(ids: frozenset[int], super_id: int | None) -> tuple[str, object]:
    lines: list[str] = []
    if super_id is not None:
        lines.append(f"<code>{super_id}</code> {_('admins.super_suffix')}")
    removable = sorted(user_id for user_id in ids if user_id != super_id)
    if removable:
        lines.extend(f"<code>{user_id}</code>" for user_id in removable)
    elif not ids:
        lines.append(_("admins.empty"))
    text = f"{_('admins.title')}\n\n" + "\n".join(lines)
    markup = admins_kb(
        removable_ids=removable,
        add_text=_("admins.btn_add"),
        remove_prefix=_("admins.btn_remove"),
        back_text=_("menu.btn_back"),
    )
    return text, markup


async def _render_panel(
    *,
    callback: CallbackQuery,
    state: FSMContext,
    admins: AdminIdsRepository,
) -> None:
    await state.set_state(None)
    text, markup = _panel_view(await admins.all(), await admins.super_id())
    await show_panel(callback=callback, text=text, markup=markup, state=state)


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.ADMINS), _is_super_admin)
async def open_admins(
    callback: CallbackQuery,
    state: FSMContext,
    admins: AdminIdsRepository,
) -> None:
    await _render_panel(callback=callback, state=state, admins=admins)


@router.callback_query(AdminAddCB.filter(), _is_super_admin)
async def prompt_add_admin(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ManageAdmins.awaiting_user_id)
    await show_panel(
        callback=callback,
        text=_("admins.add_prompt"),
        markup=admin_cancel_kb(cancel_text=_("menu.btn_cancel")),
        state=state,
    )


@router.callback_query(AdminCancelCB.filter(), _is_super_admin)
async def cancel_admin(
    callback: CallbackQuery,
    state: FSMContext,
    admins: AdminIdsRepository,
) -> None:
    await _render_panel(callback=callback, state=state, admins=admins)


@router.callback_query(AdminRemoveCB.filter(), _is_super_admin)
async def remove_admin(
    callback: CallbackQuery,
    callback_data: AdminRemoveCB,
    state: FSMContext,
    admins: AdminIdsRepository,
) -> None:
    if await admins.is_super(user_id=callback_data.user_id):
        await callback.answer(_("admins.cannot_remove_super"), show_alert=True)
        return
    current = await admins.all()
    if callback_data.user_id not in current:
        await callback.answer(_("admins.not_found"), show_alert=True)
        return
    await admins.remove(user_id=callback_data.user_id)
    await _render_panel(callback=callback, state=state, admins=admins)


@router.message(ManageAdmins.awaiting_user_id, F.text, _is_super_admin)
async def add_admin(
    message: Message,
    state: FSMContext,
    admins: AdminIdsRepository,
) -> None:
    user_id = _parse_id(message.text or "")
    if user_id is None:
        await message.answer(_("admins.invalid_id"))
        return
    if await admins.is_super(user_id=user_id):
        await message.answer(_("admins.already"))
        await state.set_state(None)
        text, markup = _panel_view(await admins.all(), await admins.super_id())
        await message.answer(text, reply_markup=markup)
        return
    current = await admins.all()
    if user_id in current:
        await message.answer(_("admins.already"))
    else:
        await admins.add(user_id=user_id)
        await message.answer(_("admins.added").format(user_id=user_id))
    await state.set_state(None)
    text, markup = _panel_view(await admins.all(), await admins.super_id())
    await message.answer(text, reply_markup=markup)


def _parse_id(raw: str) -> int | None:
    text = raw.strip()
    if not text.isdigit():
        return None
    value = int(text)
    if value <= 0:
        return None
    return value
