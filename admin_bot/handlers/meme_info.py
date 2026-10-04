import asyncio

from aiogram import F, Router
from aiogram.types import Message
from aiogram.utils.i18n import gettext as _

from admin_bot.services.media import MediaLookup
from admin_bot.services.meme import format_meme_card, post_date_from_our_public
from shared.redis import AllowedChatsRepository

router = Router(name="meme_info")


@router.message(F.forward_origin | F.forward_from_chat)
async def show_forwarded_meme(
    message: Message,
    media_lookup: MediaLookup,
    allowed_chats: AllowedChatsRepository,
    config_target_chat_id: str,
) -> None:
    posted_at = post_date_from_our_public(message, config_target_chat_id)
    if posted_at is None:
        await message.answer(_("meme.not_from_ours"))
        return
    media = await asyncio.to_thread(
        media_lookup.get_by_posted_at,
        posted_at,
    )
    if media is None:
        await message.answer(_("meme.not_found"))
        return
    chats = await allowed_chats.all()
    label = chats.get(media.chat_id)
    await message.answer(format_meme_card(media, source_label=label))
