"""
Storage module for organizing and tracking downloaded media (photos and videos).
Uses MinIO (S3-compatible) for storage and PostgreSQL metadata tracking with SQLAlchemy 2.0 Core.
"""
import hashlib
import logging
from datetime import datetime
from typing import Optional, Literal
from contextlib import contextmanager

from pydantic import BaseModel
import boto3
from botocore.exceptions import ClientError
from sqlalchemy import func, select, insert, update, case, distinct

from shared.db import Media, DatabaseManager

logger = logging.getLogger(__name__)

MediaType = Literal["photo", "video"]


class MediaMetadata(BaseModel):
    """Pydantic model for media metadata from database."""
    id: int
    media_type: MediaType
    file_hash: str
    file_path: str
    chat_id: int
    message_id: int
    sender_id: int
    sender_name: Optional[str] = None
    chat_title: Optional[str] = None
    caption: Optional[str] = None
    telegram_id: Optional[int] = None
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None  # Only for videos
    mime_type: Optional[str] = None  # Only for videos
    video_codec: Optional[str] = None  # Only for videos, e.g. "h264", "h265", "av1"
    round_message: Optional[bool] = None  # Only for videos; True if a round video note
    is_sent_tg: bool = False
    downloaded_at: datetime
    created_at: Optional[datetime] = None
    posted_at_tg: datetime | None = None
    posted_at_tiktok: datetime | None = None
    
    class Config:
        from_attributes = True


class StorageStatistics(BaseModel):
    """Pydantic model for storage statistics."""
    total_photos: int = 0
    total_videos: int = 0
    total_medias: int = 0
    total_chats: int = 0
    total_senders: int = 0
    total_size_bytes: int = 0
    first_download: Optional[datetime] = None
    last_download: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class MediaStorage:
    """
    Manages media (photos and videos) storage with MinIO (S3-compatible) and PostgreSQL metadata tracking.
    
    Media files are stored in MinIO bucket with flat structure: {hash}.{extension}
    Paths are stored in database for reference but point to S3 keys.
    
    This structure:
    - Uses S3-compatible object storage for scalability
    - Enables efficient duplicate detection via content hashing
    - Supports distributed storage and CDN integration
    - Single unified table for both photos and videos with media_type discriminator
    - Uses SQLAlchemy ORM for type-safe database operations
    """
    
    def __init__(
        self, 
        database_url: str,
        minio_endpoint: str,
        minio_access_key: str,
        minio_secret_key: str,
        minio_bucket: str,
        minio_secure: bool = False
    ):
        self.database_url = database_url
        self.minio_bucket = minio_bucket
        
        self.db_manager = DatabaseManager(database_url)
        
        self.s3_client = boto3.client(
            's3',
            endpoint_url=f"{'https' if minio_secure else 'http'}://{minio_endpoint}",
            aws_access_key_id=minio_access_key,
            aws_secret_access_key=minio_secret_key,
            region_name='us-east-1'  # MinIO doesn't care about region but boto3 requires it
        )
        
        self._init_database()
        self._init_minio_bucket()
    
    def _init_database(self) -> None:
        """Initialize PostgreSQL database with SQLAlchemy ORM."""
        self.db_manager.init_db()
        logger.info("PostgreSQL database initialized with SQLAlchemy ORM")
    
    def _init_minio_bucket(self) -> None:
        """Initialize MinIO bucket if it doesn't exist."""
        try:
            self.s3_client.head_bucket(Bucket=self.minio_bucket)
            logger.info(f"MinIO bucket '{self.minio_bucket}' already exists")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # Bucket doesn't exist, create it
                self.s3_client.create_bucket(Bucket=self.minio_bucket)
                logger.info(f"MinIO bucket '{self.minio_bucket}' created")
            else:
                logger.error(f"Error checking MinIO bucket: {e}")
                raise
    
    @contextmanager
    def _get_session(self):
        """Context manager for database sessions."""
        with self.db_manager.get_session() as session:
            yield session
    
    def _calculate_hash(self, data: bytes) -> str:
        """Calculate SHA256 hash of photo data."""
        return hashlib.sha256(data).hexdigest()
    
    def _get_s3_key(self, file_hash: str, extension: str = 'jpg') -> str:
        """
        Generate S3 key (flat structure) based on hash.
        
        Example: hash 'abc123...' -> abc123....jpg
        Uses flat structure in bucket for simplicity.
        """
        return f"{file_hash}.{extension}"
    
    def get_media_data(self, file_path: str) -> bytes:
        """
        Retrieve media (photo or video) data from MinIO.
        
        Args:
            file_path: The S3 key to the media file
            
        Returns:
            bytes: The media data
        """
        response = self.s3_client.get_object(Bucket=self.minio_bucket, Key=file_path)
        return response['Body'].read()
    
    def save_media(
        self,
        media_type: MediaType,
        media_data: bytes,
        chat_id: int,
        message_id: int,
        sender_id: int,
        sender_name: str,
        chat_title: str,
        caption: Optional[str] = None,
        telegram_id: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        duration: Optional[int] = None,
        mime_type: Optional[str] = None,
        file_extension: Optional[str] = None,
        created_at: Optional[datetime] = None,
        video_codec: Optional[str] = None,
        round_message: Optional[bool] = None
    ) -> tuple[str, bool]:
        """
        Save media (photo or video) to MinIO with flat structure and metadata tracking.
        
        Args:
            media_type: "photo" or "video"
            media_data: The media file bytes
            ... (other parameters)
        
        Returns:
            tuple[str, bool]: (file_path, is_duplicate)
                - file_path: S3 key where media is saved
                - is_duplicate: True if media already existed (based on hash)
        """
        file_hash = self._calculate_hash(media_data)
        file_size = len(media_data)
        
        # Check for duplicates
        with self._get_session() as session:
            stmt = select(Media.file_path).where(Media.file_hash == file_hash)
            result = session.execute(stmt).first()
            
            if result:
                existing_path = result[0]
                logger.info(f"Duplicate {media_type} detected (hash: {file_hash[:8]}...)")
                return existing_path, True
        
        if media_type == "photo":
            extension = file_extension or 'jpg'
            content_type = mime_type or 'image/jpeg'
        else:  # video
            extension = file_extension or 'mp4'
            content_type = mime_type or 'video/mp4'
        
        s3_key = self._get_s3_key(file_hash, extension)
        try:
            self.s3_client.put_object(
                Bucket=self.minio_bucket,
                Key=s3_key,
                Body=media_data,
                ContentType=content_type
            )
        except ClientError as e:
            logger.error(f"Error uploading {media_type} to MinIO: {e}")
            raise
        
        with self._get_session() as session:
            stmt = insert(Media).values(
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
                round_message=round_message
            )
            session.execute(stmt)
        
        logger.info(f"{media_type.capitalize()} saved to MinIO: {s3_key} (hash: {file_hash[:8]}...)")
        return s3_key, False

    def get_unsent_media(
        self, 
        limit: int = 10, 
        media_type: Optional[MediaType] = None,
        order_by: str | None = None,
        order_direction: str = 'ASC'
    ) -> list[MediaMetadata]:
        """
        Get unsent media with configurable ordering and optional media type filtering.
        
        Args:
            limit: Maximum number of media items to return
            media_type: Filter by "photo" or "video", or None for both
            order_by: Column to order by (e.g., 'downloaded_at', 'created_at', 'file_size') or None to shuffle
            order_direction: 'ASC' for ascending (oldest first) or 'DESC' for descending
            
        Returns:
            List of unsent media metadata, ordered as specified
            
        Note:
            This is an internal method - order_by and order_direction are not validated
            as they are never exposed to user input.
        """
        with self._get_session() as session:
            stmt = select(Media).where(Media.is_sent_tg == False)
            
            if media_type:
                stmt = stmt.where(Media.media_type == media_type)
            
            if order_by is None:
                stmt = stmt.order_by(func.random())
            else:
                order_column = getattr(Media, order_by)
                if order_direction.upper() == 'DESC':
                    stmt = stmt.order_by(order_column.desc())
                else:
                    stmt = stmt.order_by(order_column.asc())
            
            stmt = stmt.limit(limit)
            
            results = session.execute(stmt).scalars().all()
            return [MediaMetadata.model_validate(media) for media in results]
    
    def mark_media_as_sent(self, media_id: int) -> bool:
        """
        Mark a media item as sent.
        
        Args:
            media_id: The database ID of the media to mark as sent
            
        Returns:
            bool: True if the media was successfully marked, False if media not found
        """
        with self._get_session() as session:
            stmt = update(Media).where(Media.id == media_id).values(
                is_sent_tg=True,
                posted_at_tg=func.current_timestamp(),
            )
            result = session.execute(stmt)
            
            updated = result.rowcount > 0
            if updated:
                logger.info(f"Media #{media_id} marked as sent")
            else:
                logger.warning(f"Media #{media_id} not found")
            return updated
    
    def get_statistics(self) -> StorageStatistics:
        """Get storage statistics for all media."""
        with self._get_session() as session:
            stmt = select(
                func.count(Media.id).label('total_medias'),
                func.count(case((Media.media_type == 'photo', 1))).label('total_photos'),
                func.count(case((Media.media_type == 'video', 1))).label('total_videos'),
                func.count(distinct(Media.chat_id)).label('total_chats'),
                func.count(distinct(Media.sender_id)).label('total_senders'),
                func.coalesce(func.sum(Media.file_size), 0).label('total_size_bytes'),
                func.min(Media.downloaded_at).label('first_download'),
                func.max(Media.downloaded_at).label('last_download')
            )
            
            result = session.execute(stmt).first()
            
            if not result or result.total_medias == 0:
                return StorageStatistics()
            
            return StorageStatistics(
                total_medias=result.total_medias,
                total_photos=result.total_photos,
                total_videos=result.total_videos,
                total_chats=result.total_chats,
                total_senders=result.total_senders,
                total_size_bytes=result.total_size_bytes,
                first_download=result.first_download,
                last_download=result.last_download
            )
