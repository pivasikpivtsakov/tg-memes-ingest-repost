from datetime import datetime
from html import escape

from aiogram.types import Chat, Message, MessageOriginChannel
from aiogram.utils.i18n import gettext as _

from shared.storage import MediaMetadata


def is_our_public_chat(chat_id: int, username: str | None, target: str) -> bool:
    target = (target or "").strip()
    if not target:
        return False
    if username:
        if username.lower() == target.lower().lstrip("@"):
            return True
    try:
        return chat_id == int(target)
    except ValueError:
        return False


def is_from_our_public(message: Message, target: str) -> bool:
    origin = message.forward_origin
    if isinstance(origin, MessageOriginChannel):
        return is_our_public_chat(origin.chat.id, origin.chat.username, target)
    chat = message.forward_from_chat
    if chat is None:
        return False
    return is_our_public_chat(chat.id, chat.username, target)


def post_date_from_our_public(message: Message, target: str) -> datetime | None:
    if not is_from_our_public(message, target):
        return None
    origin = message.forward_origin
    if isinstance(origin, MessageOriginChannel):
        return origin.date
    return message.forward_date


def source_channel_from_message(message: Message) -> tuple[int, str | None] | None:
    origin = message.forward_origin
    if isinstance(origin, MessageOriginChannel):
        return origin.chat.id, origin.chat.username
    chat = message.forward_from_chat
    if chat is not None and _is_channel(chat):
        return chat.id, chat.username
    return None


def _is_channel(chat: Chat) -> bool:
    return chat.type in {"channel", "supergroup"}


def _dash() -> str:
    return _("common.dash")


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return _dash()
    return escape(value.strftime("%Y-%m-%d %H:%M:%S"))


def _fmt_size(value: int | None) -> str:
    if value is None:
        return _dash()
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value / (1024 * 1024):.1f} MB"


def _fmt_bool(value: bool | None) -> str:
    if value is None:
        return _dash()
    return _("common.yes") if value else _("common.no")


def _source_link(chat_id: int, message_id: int) -> str:
    raw = str(chat_id)
    internal = raw[4:] if raw.startswith("-100") else str(abs(chat_id))
    return f"https://t.me/c/{internal}/{message_id}"


def format_meme_card(media: MediaMetadata, *, source_label: str | None) -> str:
    source = escape(source_label or media.chat_title or str(media.chat_id))
    caption = escape(media.caption) if media.caption else _("meme.no_caption")
    sender = escape(media.sender_name) if media.sender_name else _dash()
    dimensions = _dash()
    if media.width and media.height:
        dimensions = f"{media.width}×{media.height}"
    duration = _dash() if media.duration is None else f"{media.duration}s"
    link = _source_link(media.chat_id, media.message_id)
    return _("meme.card").format(
        source=source,
        chat_id=media.chat_id,
        message_link=f'<a href="{link}">{media.message_id}</a>',
        downloaded_at=_fmt_dt(media.downloaded_at),
        created_at=_fmt_dt(media.created_at),
        posted_at_tg=_fmt_dt(media.posted_at_tg),
        media_id=media.id,
        media_type=escape(media.media_type),
        file_size=_fmt_size(media.file_size),
        dimensions=dimensions,
        duration=duration,
        mime_type=escape(media.mime_type) if media.mime_type else _dash(),
        video_codec=escape(media.video_codec) if media.video_codec else _dash(),
        round_message=_fmt_bool(media.round_message),
        sender_name=sender,
        sender_id=media.sender_id,
        caption=caption,
    )
