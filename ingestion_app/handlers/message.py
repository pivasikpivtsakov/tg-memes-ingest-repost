import logging
import os
from telethon import events, TelegramClient
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeFilename

from ingestion_app.config import config
from ingestion_app.handlers.utils import get_sender_name
from shared.storage import MediaStorage
from shared.redis import create_redis, AllowedChatsRepository

logger = logging.getLogger(__name__)

# Video size limit: 50 MB
MAX_VIDEO_SIZE_BYTES = 50 * 1024 * 1024

# Initialize media storage with MinIO and PostgreSQL metadata tracking
media_storage = MediaStorage(
    config.database_url,
    config.minio_endpoint,
    config.minio_access_key,
    config.minio_secret_key,
    config.minio_bucket,
    config.minio_secure
)

redis_client = create_redis(config.redis_url)
allowed_chats = AllowedChatsRepository(redis=redis_client)


def extract_video_attributes(video):
    """Extract width, height, duration, codec, and filename from video attributes."""
    width = height = duration = video_codec = filename = None
    for attr in video.attributes:
        if isinstance(attr, DocumentAttributeVideo):
            width, height, duration = attr.w, attr.h, attr.duration
            video_codec = attr.video_codec
        elif isinstance(attr, DocumentAttributeFilename):
            filename = attr.file_name
    return width, height, duration, video_codec, filename


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


def register_message_handler(client: TelegramClient) -> None:
    """Register new message event handler."""
    logger.info("Registering message handler")

    @client.on(events.NewMessage())
    async def handle_new_message(event: events.NewMessage.Event) -> None:
        try:
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
            
            should_save_photo = has_photo and not has_any_text and not is_repost and not has_markup
            should_save_video = has_video and not has_any_text and not is_repost and not has_markup

            logger.info(
                f"Message #{message_id} from {sender_name} (ID: {sender_id}) "
                f"in '{chat_title}' (Chat ID: {chat_id}): {message_text}"
            )
            
            # Handle photo download
            if should_save_photo:
                photo = event.message.photo
                logger.info(f"Message #{message_id} contains a photo (ID: {photo.id})")
                
                media_bytes = await client.download_media(event.message, file=bytes)
                
                # Get photo dimensions
                largest_size = max(photo.sizes, key=lambda s: getattr(s, 'size', 0))
                width = getattr(largest_size, 'w', None)
                height = getattr(largest_size, 'h', None)
                
                # Prepare photo metadata
                media_type = "photo"
                telegram_id = photo.id
                duration = None
                video_codec = None
                mime_type = 'image/jpeg'
                file_extension = 'jpg'
                created_at = photo.date
            
            # Handle video download
            elif should_save_video:
                video = event.message.video
                
                # Check video size before downloading
                if video.size > MAX_VIDEO_SIZE_BYTES:
                    logger.info(
                        f"Message #{message_id} video too large "
                        f"({video.size / (1024 * 1024):.2f} MB > 50 MB). Skipping."
                    )
                
                logger.info(
                    f"Message #{message_id} contains a video (ID: {video.id}, "
                    f"Size: {video.size / (1024 * 1024):.2f} MB)"
                )
                
                media_bytes = await client.download_media(event.message, file=bytes)
                
                # Extract video attributes
                width, height, duration, video_codec, filename = extract_video_attributes(video)
                file_extension = determine_video_extension(video, filename)
                
                # Prepare video metadata
                media_type = "video"
                telegram_id = video.id
                mime_type = video.mime_type
                created_at = video.date
            
            # Save media (unified call for both photos and videos)
            if should_save_photo or should_save_video:
                file_path, is_duplicate = media_storage.save_media(
                    media_type=media_type,
                    media_data=media_bytes,
                    chat_id=chat_id,
                    message_id=message_id,
                    sender_id=sender_id,
                    sender_name=sender_name,
                    chat_title=chat_title,
                    caption=message_text if message_text != '<non-text message>' else None,
                    telegram_id=telegram_id,
                    width=width,
                    height=height,
                    duration=duration,
                    mime_type=mime_type,
                    file_extension=file_extension,
                    created_at=created_at,
                    video_codec=video_codec
                )
                
                logger.info(f"{media_type.capitalize()} {'duplicate' if is_duplicate else 'saved'}: {file_path}")
            
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
