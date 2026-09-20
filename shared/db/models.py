"""
SQLAlchemy ORM models for media storage.
"""
from datetime import datetime
from typing import Optional, Literal

from sqlalchemy import String, Integer, BigInteger, Boolean, Text, CheckConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db.base import Base

MediaType = Literal["photo", "video"]


class Media(Base):
    """
    ORM model for media (photos and videos) metadata.
    
    Unified table for both photos and videos with media_type discriminator.
    Files are stored in MinIO (S3-compatible) storage, paths reference S3 keys.
    """
    __tablename__ = 'medias'
    
    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Media type discriminator
    media_type: Mapped[str] = mapped_column(
        String, 
        nullable=False,
        comment="Type of media: 'photo' or 'video'"
    )
    
    # File identification
    file_hash: Mapped[str] = mapped_column(
        Text, 
        unique=True, 
        nullable=False,
        comment="SHA256 hash of file content for duplicate detection"
    )
    file_path: Mapped[str] = mapped_column(
        Text, 
        nullable=False,
        comment="S3 key path to the file in MinIO bucket"
    )
    
    # Telegram metadata
    chat_id: Mapped[int] = mapped_column(
        BigInteger, 
        nullable=False,
        comment="Telegram chat/channel ID where media was found"
    )
    message_id: Mapped[int] = mapped_column(
        BigInteger, 
        nullable=False,
        comment="Telegram message ID"
    )
    sender_id: Mapped[int] = mapped_column(
        BigInteger, 
        nullable=False,
        comment="Telegram user/channel ID of the sender"
    )
    sender_name: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True,
        comment="Display name of the sender"
    )
    chat_title: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True,
        comment="Title of the chat/channel"
    )
    caption: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True,
        comment="Original caption/text from message"
    )
    telegram_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, 
        nullable=True,
        comment="Telegram's internal ID for the media file"
    )
    
    # File properties
    file_size: Mapped[Optional[int]] = mapped_column(
        Integer, 
        nullable=True,
        comment="File size in bytes"
    )
    width: Mapped[Optional[int]] = mapped_column(
        Integer, 
        nullable=True,
        comment="Media width in pixels"
    )
    height: Mapped[Optional[int]] = mapped_column(
        Integer, 
        nullable=True,
        comment="Media height in pixels"
    )
    duration: Mapped[Optional[int]] = mapped_column(
        Integer, 
        nullable=True,
        comment="Duration in seconds (videos only)"
    )
    mime_type: Mapped[str] = mapped_column(
        Text, 
        nullable=False,
        comment="MIME type of the media file"
    )
    video_codec: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Video codec reported by Telegram source (e.g. 'h264', 'h265', 'av1'); videos only"
    )
    
    # Status tracking
    is_sent_tg: Mapped[bool] = mapped_column(
        Boolean, 
        nullable=False, 
        default=False,
        server_default='false',
        comment="Whether media has been sent to Telegram target channel"
    )
    posted_at_tg: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="When media was marked sent to Telegram target channel"
    )

    is_sent_tiktok: Mapped[bool] = mapped_column(
        Boolean, 
        nullable=False, 
        default=False,
        server_default='false',
        comment="Whether media has been sent to TikTok target account"
    )
    posted_at_tiktok: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="When media was marked sent to TikTok target account"
    )
    
    # Timestamps
    downloaded_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=func.current_timestamp(),
        server_default=func.current_timestamp(),
        comment="When media was downloaded and saved"
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="Original creation timestamp from Telegram"
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "media_type IN ('photo', 'video')",
            name='check_media_type'
        ),
        # Indexes for common query patterns
        Index('idx_media_type', 'media_type'),
        Index('idx_chat_id', 'chat_id'),
        Index('idx_message_id', 'message_id'),
        Index('idx_sender_id', 'sender_id'),
        Index('idx_downloaded_at', 'downloaded_at'),
        Index('idx_file_hash', 'file_hash'),
        Index('idx_is_sent', 'is_sent_tg'),
        Index('idx_is_sent_media_type', 'is_sent_tg', 'media_type'),
    )
    
    def __repr__(self) -> str:
        return (
            f"<Media(id={self.id}, type={self.media_type}, "
            f"hash={self.file_hash[:8]}..., is_sent_tg={self.is_sent_tg})>"
        )

