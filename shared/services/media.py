import hashlib
import logging
from datetime import datetime

from botocore.exceptions import ClientError

from shared.db.models import MediaType
from shared.db.repositories.media import MediaMetadata, MediaRepository
from shared.db.session import AsyncDatabaseManager
from shared.s3.client import create_s3_client
from shared.s3.repositories import ObjectRepository

logger = logging.getLogger(__name__)


class MediaService:
    def __init__(
        self,
        database_url: str,
        minio_endpoint: str,
        minio_access_key: str,
        minio_secret_key: str,
        minio_bucket: str,
        minio_secure: bool = False,
    ):
        self._db = AsyncDatabaseManager(database_url)
        self._media = MediaRepository(self._db)
        self._objects = ObjectRepository(
            client=create_s3_client(
                endpoint=minio_endpoint,
                access_key=minio_access_key,
                secret_key=minio_secret_key,
                secure=minio_secure,
            ),
            bucket=minio_bucket,
        )
        self._ensure_bucket()

    async def dispose(self) -> None:
        await self._db.dispose()

    def _ensure_bucket(self) -> None:
        try:
            created = self._objects.ensure_bucket()
        except ClientError as e:
            logger.error(f"Error checking MinIO bucket: {e}")
            raise
        if created:
            logger.info(f"MinIO bucket '{self._objects.bucket}' created")
        else:
            logger.info(f"MinIO bucket '{self._objects.bucket}' already exists")

    def _calculate_hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def get_media_data(self, file_path: str) -> bytes:
        return self._objects.get(file_path)

    async def save_media(
        self,
        media_type: MediaType,
        media_data: bytes,
        chat_id: int,
        message_id: int,
        sender_id: int,
        sender_name: str,
        chat_title: str,
        telegram_id: int,
        created_at: datetime,
        caption: str | None = None,
        width: int | None = None,
        height: int | None = None,
        duration: int | None = None,
        mime_type: str | None = None,
        file_extension: str | None = None,
        video_codec: str | None = None,
        round_message: bool | None = None,
        video_sticker: bool = False,
        grouped_id: int | None = None,
        album_position: int | None = None,
    ) -> tuple[str, bool]:
        file_hash = self._calculate_hash(media_data)
        file_size = len(media_data)

        existing_path = await self._media.get_path_by_hash(file_hash)
        if existing_path is not None:
            logger.info(f"Duplicate {media_type} detected (hash: {file_hash[:8]}...)")
            return existing_path, True

        if media_type == MediaType.PHOTO:
            extension = file_extension or "jpg"
            content_type = mime_type or "image/jpeg"
        else:
            extension = file_extension or "mp4"
            content_type = mime_type or "video/mp4"

        s3_key = self._objects.key_for(file_hash, extension)
        try:
            self._objects.put(s3_key, body=media_data, content_type=content_type)
        except ClientError as e:
            logger.error(f"Error uploading {media_type} to MinIO: {e}")
            raise

        await self._media.insert(
            media_type=media_type,
            file_hash=file_hash,
            file_path=s3_key,
            chat_id=chat_id,
            message_id=message_id,
            sender_id=sender_id,
            sender_name=sender_name,
            chat_title=chat_title,
            caption=caption,
            telegram_id=telegram_id,
            file_size=file_size,
            width=width,
            height=height,
            duration=duration,
            mime_type=mime_type,
            created_at=created_at,
            video_codec=video_codec,
            round_message=round_message,
            video_sticker=video_sticker,
            grouped_id=grouped_id,
            album_position=album_position,
        )

        logger.info(f"{media_type.capitalize()} saved to MinIO: {s3_key} (hash: {file_hash[:8]}...)")
        return s3_key, False

    async def get_unsent_media(
        self,
        media_type: MediaType | None = None,
        order_by: str | None = None,
        order_direction: str = "ASC",
    ) -> MediaMetadata | None:
        return await self._media.get_unsent(
            media_type=media_type,
            order_by=order_by,
            order_direction=order_direction,
        )

    async def mark_media_as_sent(
        self,
        media_id: int,
        *,
        posted_message_id: int | None = None,
    ) -> bool:
        updated = await self._media.mark_as_sent(
            media_id,
            posted_message_id=posted_message_id,
        )
        if updated:
            logger.info(f"Media #{media_id} marked as sent")
        else:
            logger.warning(f"Media #{media_id} not found")
        return updated

    async def mark_medias_as_sent(
        self,
        media_ids: list[int],
        posted_message_ids: dict[int, int] | None = None,
    ) -> int:
        if not media_ids:
            return 0
        updated = await self._media.mark_many_as_sent(
            media_ids,
            posted_message_ids=posted_message_ids,
        )
        if updated:
            logger.info(f"Media {media_ids} marked as sent")
        else:
            logger.warning(f"Media {media_ids} not found")
        return updated

    async def get_unsent_album_siblings(
        self,
        chat_id: int,
        grouped_id: int,
    ) -> list[MediaMetadata]:
        return await self._media.list_unsent_album_siblings(
            chat_id=chat_id,
            grouped_id=grouped_id,
        )

    async def find_media_by_where(self, where_expr: str) -> list[MediaMetadata]:
        return await self._media.list_by_where(where_expr)

    def delete_object(self, file_path: str) -> None:
        try:
            self._objects.delete(file_path)
        except ClientError as e:
            logger.error(f"Error deleting MinIO object {file_path}: {e}")
            raise
        logger.info(f"Deleted MinIO object: {file_path}")

    async def get_media_by_id(self, media_id: int) -> MediaMetadata:
        return await self._media.get_by_id(media_id)

    async def delete_media_row(self, media_id: int) -> bool:
        deleted = await self._media.delete_by_id(media_id)
        if deleted:
            logger.info(f"Media #{media_id} deleted from database")
        else:
            logger.warning(f"Media #{media_id} not found in database")
        return deleted
