import logging
import os
from telethon import events, TelegramClient
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeFilename, DocumentAttributeSticker

from ingestion_app.config import config
from shared.redis import create_redis
from shared.services import AllowedChatsService, MediaService

logger = logging.getLogger(__name__)

# Video size limit: 50 MB
MAX_VIDEO_SIZE_BYTES = 50 * 1024 * 1024

media_service = MediaService(
    config.database_url,
    config.minio_endpoint,
    config.minio_access_key,
    config.minio_secret_key,
    config.minio_bucket,
    config.minio_secure
)

redis_client = create_redis(config.redis_url)
allowed_chats = AllowedChatsService(redis=redis_client)


def get_sender_name(sender) -> str:
    if getattr(sender, 'first_name', None) and getattr(sender, 'last_name', None):
        return f"{sender.first_name} {sender.last_name}"
    if getattr(sender, 'title', None):
        return sender.title
    return 'Unknown'


def extract_video_attributes(video):
    """Extract width, height, duration, codec, round/sticker flags, and filename from video attributes."""
    width = height = duration = video_codec = round_message = filename = None
    video_sticker = False
    for attr in video.attributes:
        if isinstance(attr, DocumentAttributeVideo):
            width, height, duration = attr.w, attr.h, attr.duration
            video_codec = attr.video_codec
            round_message = attr.round_message
        elif isinstance(attr, DocumentAttributeFilename):
            filename = attr.file_name
        elif isinstance(attr, DocumentAttributeSticker):
            video_sticker = True
    if not video_sticker and (getattr(video, 'mime_type', None) or '').lower() == 'video/webm':
        video_sticker = True
    return width, height, duration, video_codec, round_message, video_sticker, filename


def determine_video_extension(video, filename):
    """Determine video file extension from filename or mime_type."""
    file_ext = 'mp4'
    if filename:
        _, ext = os.path.splitext(filename)
        if ext and len(ext) > 1:
            file_ext = ext[1:].lower()
    elif video.mime_type:
        mime_parts = video.mime_type.lower().split('/')
        if len(mime_parts) == 2 and mime_parts[1] in ['mp4', 'webm', 'mov', 'avi', 'mkv', 'quicktime']:
            file_ext = 'mov' if mime_parts[1] == 'quicktime' else mime_parts[1]
    return file_ext


async def save_media_from_message(
    client: TelegramClient,
    message,
    *,
    chat_id: int,
    sender_id: int,
    sender_name: str,
    chat_title: str,
    grouped_id: int | None = None,
    album_position: int | None = None,
) -> None:
    """Download and persist photo/video from a Telegram message."""
    message_id = message.id

    if message.photo:
        photo = message.photo
        logger.info(f"Message #{message_id} contains a photo (ID: {photo.id})")

        media_bytes = await client.download_media(message, file=bytes)

        largest_size = max(photo.sizes, key=lambda s: getattr(s, 'size', 0))
        width = getattr(largest_size, 'w', None)
        height = getattr(largest_size, 'h', None)

        media_type = "photo"
        telegram_id = photo.id
        duration = None
        video_codec = None
        round_message = None
        video_sticker = False
        mime_type = 'image/jpeg'
        file_extension = 'jpg'
        created_at = photo.date
    elif message.video:
        video = message.video

        if video.size > MAX_VIDEO_SIZE_BYTES:
            logger.info(
                f"Message #{message_id} video too large "
                f"({video.size / (1024 * 1024):.2f} MB > 50 MB). Skipping."
            )
            return

        logger.info(
            f"Message #{message_id} contains a video (ID: {video.id}, "
            f"Size: {video.size / (1024 * 1024):.2f} MB)"
        )

        media_bytes = await client.download_media(message, file=bytes)

        width, height, duration, video_codec, round_message, video_sticker, filename = extract_video_attributes(video)
        file_extension = determine_video_extension(video, filename)

        media_type = "video"
        telegram_id = video.id
        mime_type = video.mime_type
        created_at = video.date
    else:
        return

    file_path, is_duplicate = await media_service.save_media(
        media_type=media_type,
        media_data=media_bytes,
        chat_id=chat_id,
        message_id=message_id,
        sender_id=sender_id,
        sender_name=sender_name,
        chat_title=chat_title,
        caption=message.text or None,
        telegram_id=telegram_id,
        width=width,
        height=height,
        duration=duration,
        mime_type=mime_type,
        file_extension=file_extension,
        created_at=created_at,
        video_codec=video_codec,
        round_message=round_message,
        video_sticker=video_sticker,
        grouped_id=grouped_id,
        album_position=album_position,
    )

    logger.info(f"{media_type.capitalize()} {'duplicate' if is_duplicate else 'saved'}: {file_path}")


def register_message_handler(client: TelegramClient) -> None:
    """Register new message and album event handlers."""
    logger.info("Registering message handler")

    @client.on(events.NewMessage())
    async def handle_new_message(event: events.NewMessage.Event) -> None:
        try:
            # Skip album messages
            if event.message.grouped_id is not None:
                return

            chat_id = event.chat_id
            if not await allowed_chats.is_allowed(chat_id=chat_id):
                return

            sender = await event.get_sender()
            chat = await event.get_chat()
            
            # sender.id is always present on all entities
            sender_id = sender.id
            
            # Users have first_name and last_name, Channels have title
            sender_name = get_sender_name(sender)
            
            # Groups/Channels have title, private chats (User) don't
            chat_title = getattr(chat, 'title', 'Private Chat')

            message_text = event.message.text or '<non-text message>'
            message_id = event.message.id
            
            # Check if message contains a photo
            has_photo = bool(event.message.photo)
            
            # Check if message contains a video (not document)
            has_video = bool(event.message.video)

            # Check if message contains text
            has_any_text = bool(event.message.text)
            
            # Check if message is a repost (forwarded message)
            is_repost = bool(event.message.fwd_from)

            has_markup = bool(event.message.reply_markup)
            
            should_save = (
                (has_photo or has_video)
                and not has_any_text
                and not is_repost
                and not has_markup
            )

            logger.info(
                f"Message #{message_id} from {sender_name} (ID: {sender_id}) "
                f"in '{chat_title}' (Chat ID: {chat_id}): {message_text}"
            )
            
            if should_save:
                await save_media_from_message(
                    client,
                    event.message,
                    chat_id=chat_id,
                    sender_id=sender_id,
                    sender_name=sender_name,
                    chat_title=chat_title,
                )
            
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)

    @client.on(events.Album())
    async def handle_album(event: events.Album.Event) -> None:
        try:
            chat_id = event.chat_id
            if not await allowed_chats.is_allowed(chat_id=chat_id):
                return

            sender = await event.get_sender()
            chat = await event.get_chat()
            sender_id = sender.id
            sender_name = get_sender_name(sender)
            chat_title = getattr(chat, 'title', 'Private Chat')
            grouped_id = event.grouped_id

            has_any_text = any(message.text for message in event.messages)
            is_repost = any(message.fwd_from for message in event.messages)
            has_markup = any(message.reply_markup for message in event.messages)

            logger.info(
                f"Album {grouped_id} from {sender_name} (ID: {sender_id}) "
                f"in '{chat_title}' (Chat ID: {chat_id}): {len(event.messages)} items"
            )

            if has_any_text or is_repost or has_markup:
                logger.info(
                    f"Album {grouped_id} skipped "
                    f"(text={bool(has_any_text)}, forward={is_repost}, markup={has_markup})"
                )
                return

            eligible = []
            for position, message in enumerate(event.messages):
                if message.photo:
                    eligible.append((position, message))
                elif message.video:
                    if message.video.size > MAX_VIDEO_SIZE_BYTES:
                        logger.info(
                            f"Message #{message.id} video too large "
                            f"({message.video.size / (1024 * 1024):.2f} MB > 50 MB). Skipping."
                        )
                        continue
                    eligible.append((position, message))

            if not eligible:
                return

            use_album = len(eligible) >= 2
            for position, message in eligible:
                try:
                    await save_media_from_message(
                        client,
                        message,
                        chat_id=chat_id,
                        sender_id=sender_id,
                        sender_name=sender_name,
                        chat_title=chat_title,
                        grouped_id=grouped_id if use_album else None,
                        album_position=position if use_album else None,
                    )
                except Exception as e:
                    logger.error(
                        f"Error saving album {grouped_id} item #{message.id}: {e}",
                        exc_info=True,
                    )

        except Exception as e:
            logger.error(f"Error handling album: {e}", exc_info=True)
