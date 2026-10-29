import asyncio
import logging
from io import BytesIO

from telethon import TelegramClient
from telethon.errors import FloodWaitError, FileReferenceExpiredError, MediaEmptyError
from telethon.tl.types import (
    Message,
    DocumentAttributeVideo,
    DocumentAttributeSticker,
    InputStickerSetEmpty,
)

from sender_tg_app.services.video_thumbnail import generate_video_thumbnail, needs_own_thumbnail
from shared.db.models import MediaType
from shared.services.media import MediaMetadata, MediaService

logger = logging.getLogger(__name__)


class MemesSender:
    def __init__(
        self, 
        client: TelegramClient, 
        media_service: MediaService,
        target_chat_id: str,
        include_caption: bool = True
    ):
        self.client = client
        self.media_service = media_service
        self.target_chat_id = target_chat_id
        self.include_caption = include_caption
        self._resolved_entity = None
    
    async def _ensure_entity_resolved(self):
        """Resolve the target entity if not already resolved."""
        if self._resolved_entity is None:
            try:
                entity_id = int(self.target_chat_id)
                logger.info(f"Resolving entity for: {entity_id}")
                self._resolved_entity = await self.client.get_entity(entity_id)
                logger.info(f"Successfully resolved entity: {self._resolved_entity.title if hasattr(self._resolved_entity, 'title') else entity_id}")
            except Exception as e:
                logger.error(f"Failed to resolve entity {self.target_chat_id}: {e}")
                raise
        return self._resolved_entity
    
    async def send_meme(self) -> bool | None:
        """
        Send one unsent meme to the configured channel.

        Returns:
            True if sent, False if send failed, None if there is nothing to send.
        """
        logger.info(f"Attempting to send a meme to {self.target_chat_id}")
        
        await self._ensure_entity_resolved()

        media = await self.media_service.get_unsent_media()

        if media is None:
            logger.info("No unsent memes found in database")
            return None

        logger.info(f"Found unsent {media.media_type} #{media.id} to send")
        return await self._send_media(media)

    async def _send_media(self, media: MediaMetadata) -> bool:
        """Send a standalone media item or the unsent remainder of its album."""
        if media.grouped_id is None:
            return await self._send_single_meme(media)

        siblings = await self.media_service.get_unsent_album_siblings(
            chat_id=media.chat_id,
            grouped_id=media.grouped_id,
        )
        if len(siblings) >= 2:
            logger.info(
                f"Sending album grouped_id={media.grouped_id} "
                f"({len(siblings)} unsent items)"
            )
            return await self._send_album(siblings)
        if len(siblings) == 1:
            return await self._send_single_meme(siblings[0])
        return await self._send_single_meme(media)
    
    async def _build_own_thumbnail_if_needed(self, media: MediaMetadata, media_data: bytes) -> BytesIO | None:
        if not needs_own_thumbnail(len(media_data)):
            return None
        try:
            thumb_data = await asyncio.to_thread(generate_video_thumbnail, media_data)
        except Exception as e:
            logger.warning(f"Failed to generate thumbnail for video #{media.id}: {e}. Sending without thumbnail")
            return None
        thumb_buffer = BytesIO(thumb_data)
        thumb_buffer.name = "thumb.jpg"
        logger.info(f"Generated own thumbnail for video #{media.id} ({len(thumb_data)} bytes)")
        return thumb_buffer

    async def _send_single_meme(self, media: MediaMetadata) -> bool:
        """
        Send a single meme (photo or video) to the target channel.
        
        Args:
            media: MediaMetadata object with file information
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        media_type = media.media_type
        is_video = media_type == MediaType.VIDEO
        
        # Retrieve media data from MinIO
        try:
            media_data = self.media_service.get_media_data(media.file_path)
        except Exception as e:
            logger.warning(
                f"{media_type.capitalize()} #{media.id} could not be retrieved from MinIO "
                f"(key: {media.file_path}): {e}. Marking as sent to avoid retrying"
            )
            await self.media_service.mark_media_as_sent(media.id)
            return False
        
        # Prepare caption
        caption = None
        if self.include_caption and media.caption:
            caption = media.caption
        
        # Log attempt
        caption_preview = f" with caption: '{caption[:50]}...'" if caption else ""
        logger.info(
            f"Sending {media_type} #{media.id} ({media.file_path}) "
            f"to {self.target_chat_id}{caption_preview}"
        )
        
        try:
            # Wrap bytes in BytesIO with .name attribute so Telethon can detect the file type
            # When passing raw bytes, Telethon's utils.is_image() or is_video() returns False
            # because there's no filename/extension to check. By wrapping in BytesIO with .name,
            # Telethon will detect the correct media type and send as the appropriate type
            # (InputMediaUploadedPhoto for images, InputMediaUploadedDocument for videos)
            file_buffer = BytesIO(media_data)
            file_buffer.name = media.file_path  # e.g., "abc123....jpg" or "def456....mp4"
            
            # For videos, we want to send as video (supports_streaming=True)
            # For photos, force_document=False ensures it's sent as a photo
            kwargs = {
                'entity': self._resolved_entity,
                'file': file_buffer,
                'caption': caption,
                'force_document': False
            }
            
            if is_video:
                # Add video-specific attributes
                kwargs['supports_streaming'] = True
                is_round = bool(media.round_message)
                if is_round:
                    kwargs['video_note'] = True
                if media.video_sticker:
                    kwargs['mime_type'] = media.mime_type or 'video/webm'
                    kwargs['nosound_video'] = True
                # if we know the width and height, we add it explicitly. 
                # telethon or telegram should not try to guess and repair it.
                # they often do it wrong.
                if media.width and media.height and media.width > 1 and media.height > 1:
                    kwargs['attributes'] = [
                        DocumentAttributeVideo(
                            duration=media.duration or 0,
                            w=media.width,
                            h=media.height,
                            supports_streaming=True,
                            video_codec=media.video_codec,
                            round_message=is_round,
                            nosound=True if media.video_sticker else None,
                        )
                    ]
                    if media.video_sticker:
                        kwargs['attributes'].append(
                            DocumentAttributeSticker(alt='', stickerset=InputStickerSetEmpty())
                        )
                thumb = await self._build_own_thumbnail_if_needed(media=media, media_data=media_data)
                if thumb is not None:
                    kwargs['thumb'] = thumb

            message: Message = await self.client.send_file(**kwargs)

            await self.media_service.mark_media_as_sent(media.id)
            
            logger.info(
                f"✓ Successfully sent {media_type} #{media.id} "
                f"(message ID: {message.id}, chat: {self.target_chat_id})"
            )
            return True
            
        except FloodWaitError as e:
            # Telegram rate limiting - need to wait
            logger.error(
                f"FloodWaitError: Telegram requires waiting {e.seconds} seconds. "
                f"{media_type.capitalize()} #{media.id} NOT marked as sent. Please try again later."
            )
            return False
            
        except (FileReferenceExpiredError, MediaEmptyError) as e:
            # File reference issues - mark as sent to avoid infinite retries
            logger.error(
                f"Telegram media error for {media_type} #{media.id}: {e}. "
                f"Marking as sent to avoid retries."
            )
            await self.media_service.mark_media_as_sent(media.id)
            return False
            
        except Exception as e:
            # Generic error - don't mark as sent, allow retry
            logger.error(
                f"Failed to send {media_type} #{media.id}: {e}. "
                f"NOT marked as sent, will retry on next run."
            )
            return False

    async def _send_album(self, medias: list[MediaMetadata]) -> bool:
        """Send unsent album items together. MinIO failures are skipped like singles."""
        file_buffers: list[BytesIO] = []
        attempt_ids: list[int] = []

        for media in medias:
            try:
                media_data = self.media_service.get_media_data(media.file_path)
            except Exception as e:
                logger.warning(
                    f"{media.media_type.capitalize()} #{media.id} could not be retrieved from MinIO "
                    f"(key: {media.file_path}): {e}. Marking as sent to avoid retrying"
                )
                await self.media_service.mark_media_as_sent(media.id)
                continue

            file_buffer = BytesIO(media_data)
            file_buffer.name = media.file_path
            file_buffers.append(file_buffer)
            attempt_ids.append(media.id)

        if not file_buffers:
            return False
        if len(file_buffers) == 1:
            remaining = next(media for media in medias if media.id == attempt_ids[0])
            return await self._send_single_meme(remaining)

        ids_preview = ", ".join(f"#{media_id}" for media_id in attempt_ids)
        logger.info(
            f"Sending album ({len(file_buffers)} files: {ids_preview}) "
            f"to {self.target_chat_id}"
        )

        try:
            await self.client.send_file(
                entity=self._resolved_entity,
                file=file_buffers,
                force_document=False,
                supports_streaming=True,
            )
            await self.media_service.mark_medias_as_sent(attempt_ids)
            logger.info(
                f"✓ Successfully sent album ({ids_preview}) to {self.target_chat_id}"
            )
            return True

        except FloodWaitError as e:
            logger.error(
                f"FloodWaitError: Telegram requires waiting {e.seconds} seconds. "
                f"Album ({ids_preview}) NOT marked as sent. Please try again later."
            )
            return False

        except (FileReferenceExpiredError, MediaEmptyError) as e:
            logger.error(
                f"Telegram media error for album ({ids_preview}): {e}. "
                f"Marking as sent to avoid retries."
            )
            await self.media_service.mark_medias_as_sent(attempt_ids)
            return False

        except Exception as e:
            logger.error(
                f"Failed to send album ({ids_preview}): {e}. "
                f"NOT marked as sent, will retry on next run."
            )
            return False

