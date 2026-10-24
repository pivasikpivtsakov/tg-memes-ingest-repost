from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import delete, func, insert, select, text, update

from shared.db.models import Media, MediaType
from shared.db.repositories.base import PostgresRepository


class MediaMetadata(BaseModel):
    id: int
    media_type: MediaType
    file_hash: str
    file_path: str
    chat_id: int
    message_id: int
    sender_id: int
    sender_name: str
    chat_title: str
    caption: str | None = None
    telegram_id: int
    grouped_id: int | None = None
    album_position: int | None = None
    file_size: int
    width: int | None = None
    height: int | None = None
    duration: int | None = None
    mime_type: str | None = None
    video_codec: str | None = None
    round_message: bool | None = None
    video_sticker: bool = False
    is_sent_tg: bool = False
    downloaded_at: datetime
    created_at: datetime
    posted_at_tg: datetime | None = None
    posted_at_tiktok: datetime | None = None

    class Config:
        from_attributes = True


class MediaRepository(PostgresRepository):
    @staticmethod
    def _to_metadata(media: Media) -> MediaMetadata:
        return MediaMetadata.model_validate(media)

    async def get_path_by_hash(self, file_hash: str) -> str | None:
        async with self._session() as session:
            result = await session.execute(
                select(Media.file_path).where(Media.file_hash == file_hash)
            )
            row = result.first()
            if row is None:
                return None
            return row[0]

    async def insert(
        self,
        *,
        media_type: MediaType,
        file_hash: str,
        file_path: str,
        chat_id: int,
        message_id: int,
        sender_id: int,
        sender_name: str,
        chat_title: str,
        caption: str | None,
        telegram_id: int,
        file_size: int,
        width: int | None,
        height: int | None,
        duration: int | None,
        mime_type: str | None,
        created_at: datetime,
        video_codec: str | None,
        round_message: bool | None,
        video_sticker: bool,
        grouped_id: int | None,
        album_position: int | None,
    ) -> None:
        stmt = insert(Media).values({
            Media.media_type.key: media_type,
            Media.file_hash.key: file_hash,
            Media.file_path.key: file_path,
            Media.chat_id.key: chat_id,
            Media.message_id.key: message_id,
            Media.sender_id.key: sender_id,
            Media.sender_name.key: sender_name,
            Media.chat_title.key: chat_title,
            Media.caption.key: caption,
            Media.telegram_id.key: telegram_id,
            Media.file_size.key: file_size,
            Media.width.key: width,
            Media.height.key: height,
            Media.duration.key: duration,
            Media.mime_type.key: mime_type,
            Media.created_at.key: created_at,
            Media.video_codec.key: video_codec,
            Media.round_message.key: round_message,
            Media.video_sticker.key: video_sticker,
            Media.grouped_id.key: grouped_id,
            Media.album_position.key: album_position,
        })
        async with self._session() as session:
            await session.execute(stmt)

    async def get_unsent(
        self,
        media_type: MediaType | None = None,
        order_by: str | None = None,
        order_direction: str = "ASC",
    ) -> MediaMetadata | None:
        async with self._session() as session:
            stmt = select(Media).where(Media.is_sent_tg == False)

            if media_type:
                stmt = stmt.where(Media.media_type == media_type)

            if order_by is None:
                stmt = stmt.order_by(func.random())
            else:
                order_column = getattr(Media, order_by)
                if order_direction.upper() == "DESC":
                    stmt = stmt.order_by(order_column.desc())
                else:
                    stmt = stmt.order_by(order_column.asc())

            media = (await session.execute(stmt.limit(1))).scalar_one_or_none()
            if media is None:
                return None
            return self._to_metadata(media)

    async def mark_as_sent(self, media_id: int) -> bool:
        async with self._session() as session:
            stmt = (
                update(Media)
                .where(Media.id == media_id)
                .values({
                    Media.is_sent_tg.key: True,
                    Media.posted_at_tg.key: func.current_timestamp(),
                })
            )
            result = await session.execute(stmt)
            return result.rowcount > 0

    async def mark_many_as_sent(self, media_ids: list[int]) -> int:
        if not media_ids:
            return 0
        async with self._session() as session:
            stmt = (
                update(Media)
                .where(Media.id.in_(media_ids))
                .values({
                    Media.is_sent_tg.key: True,
                    Media.posted_at_tg.key: func.current_timestamp(),
                })
            )
            result = await session.execute(stmt)
            return result.rowcount or 0

    async def list_unsent_album_siblings(
        self,
        chat_id: int,
        grouped_id: int,
    ) -> list[MediaMetadata]:
        async with self._session() as session:
            stmt = (
                select(Media)
                .where(
                    Media.chat_id == chat_id,
                    Media.grouped_id == grouped_id,
                    Media.is_sent_tg == False,
                )
                .order_by(Media.album_position.asc(), Media.id.asc())
            )
            results = await session.execute(stmt)
            return [self._to_metadata(media) for media in results.scalars().all()]

    async def list_by_where(self, where_expr: str) -> list[MediaMetadata]:
        where_expr = where_expr.strip()
        if not where_expr:
            raise ValueError("WHERE expression must not be empty")
        if ";" in where_expr:
            raise ValueError("WHERE expression must be a single clause")

        async with self._session() as session:
            stmt = select(Media).where(text(f"({where_expr})")).order_by(Media.id.asc())
            results = await session.execute(stmt)
            return [self._to_metadata(media) for media in results.scalars().all()]

    async def get_by_id(self, media_id: int) -> MediaMetadata:
        async with self._session() as session:
            result = await session.execute(select(Media).where(Media.id == media_id))
            return self._to_metadata(result.scalar_one())

    async def list_by_ids(self, media_ids: list[int]) -> dict[int, MediaMetadata]:
        if not media_ids:
            return {}
        async with self._session() as session:
            results = await session.execute(select(Media).where(Media.id.in_(media_ids)))
            return {media.id: self._to_metadata(media) for media in results.scalars().all()}

    async def delete_by_id(self, media_id: int) -> bool:
        async with self._session() as session:
            result = await session.execute(delete(Media).where(Media.id == media_id))
            return result.rowcount > 0

    async def list_by_posted_at_range(
        self,
        start: datetime,
        end: datetime,
    ) -> list[MediaMetadata]:
        async with self._session() as session:
            result = await session.execute(
                select(Media).where(
                    Media.posted_at_tg >= start,
                    Media.posted_at_tg <= end,
                )
            )
            return [self._to_metadata(media) for media in result.scalars().all()]
