import logging
from io import BytesIO
from dataclasses import dataclass

from telethon import TelegramClient
from telethon.errors import FloodWaitError, FileReferenceExpiredError, MediaEmptyError
from telethon.tl.types import Message, DocumentAttributeVideo

from shared.storage import MediaStorage, MediaMetadata

logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    """Result of sending a batch of memes."""
    total_requested: int
    sent_successfully: int
    failed: int
    no_unsent_memes: bool
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_requested == 0:
            return 0.0
        return (self.sent_successfully / self.total_requested) * 100


class MemesSender:
    """Service for sending memes from storage to Telegram channels."""
    
    def __init__(
        self, 
        client: TelegramClient, 
        storage: MediaStorage,
        target_chat_id: str,
        include_caption: bool = True
    ):
        self.client = client
        self.storage = storage
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
    
    async def send_memes(self, count: int = 1) -> SendResult:
        """
        Send N unsent memes (photos and videos) to the configured channel.
        
        Args:
            count: Number of memes to send (default: 1)
            
        Returns:
            SendResult with statistics about the operation
        """
        logger.info(f"Attempting to send {count} meme(s) to {self.target_chat_id}")
        
        # Ensure the target entity is resolved before sending
        await self._ensure_entity_resolved()
        
        # Get unsent media from unified table (automatically sorted by downloaded_at, oldest first)
        unsent_media = self.storage.get_unsent_media(
            limit=count,
            order_by=None,
            order_direction='ASC',
        )

        if not unsent_media:
            logger.info("No unsent memes found in database")
            return SendResult(
                total_requested=count,
                sent_successfully=0,
                failed=0,
                no_unsent_memes=True
            )
        
        logger.info(
            f"Found {len(unsent_media)} unsent meme(s) to send "
            f"({sum(1 for m in unsent_media if m.media_type == 'photo')} photos, "
            f"{sum(1 for m in unsent_media if m.media_type == 'video')} videos)"
        )
        
        sent_successfully = 0
        failed = 0
        
        for media in unsent_media:
            try:
                success = await self._send_single_meme(media)
                if success:
                    sent_successfully += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Unexpected error sending {media.media_type} #{media.id}: {e}", exc_info=True)
                failed += 1
        
        result = SendResult(
            total_requested=count,
            sent_successfully=sent_successfully,
            failed=failed,
            no_unsent_memes=False
        )
        
        logger.info(
            f"Sending complete: {sent_successfully}/{len(unsent_media)} successful, "
            f"{failed} failed ({result.success_rate:.1f}% success rate)"
        )
        
        return result
    
    async def _send_single_meme(self, media: MediaMetadata) -> bool:
        """
        Send a single meme (photo or video) to the target channel.
        
        Args:
            media: MediaMetadata object with file information
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        media_type = media.media_type
        is_video = (media_type == "video")
        
        # Retrieve media data from MinIO
        try:
            media_data = self.storage.get_media_data(media.file_path)
        except Exception as e:
            logger.warning(
                f"{media_type.capitalize()} #{media.id} could not be retrieved from MinIO "
                f"(key: {media.file_path}): {e}. Marking as sent to avoid retrying"
            )
            self.storage.mark_media_as_sent(media.id)
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
                        )
                    ]

            message: Message = await self.client.send_file(**kwargs)
            
            # Mark as sent in database
            self.storage.mark_media_as_sent(media.id)
            
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
            self.storage.mark_media_as_sent(media.id)
            return False
            
        except Exception as e:
            # Generic error - don't mark as sent, allow retry
            logger.error(
                f"Failed to send {media_type} #{media.id}: {e}. "
                f"NOT marked as sent, will retry on next run."
            )
            return False

