from abc import ABC, abstractmethod
from collections.abc import Collection
from typing import ClassVar, Literal

from sqlalchemy import exists, func, select

from shared.db.models import Media, MediaClipEmbedding, MediaOcr
from shared.db.repositories.base import PostgresRepository
from shared.db.repositories.media import MediaMetadata

IndexOrder = Literal["asc", "desc"]


class MediaIndexRepository[RowT](PostgresRepository, ABC):
    """A table keyed by media_id; a media without a row there is not indexed yet."""

    index_model: ClassVar[type[MediaClipEmbedding] | type[MediaOcr]]

    @abstractmethod
    async def insert_many(self, rows: list[RowT]) -> int:
        """Insert rows, skipping medias another indexer process already stored."""

    def _not_indexed(self):
        return ~exists().where(self.index_model.media_id == Media.id)

    async def list_missing(
        self,
        *,
        limit: int,
        order: IndexOrder,
        exclude_ids: Collection[int] = (),
    ) -> list[MediaMetadata]:
        stmt = select(Media).where(self._not_indexed())
        if exclude_ids:
            stmt = stmt.where(Media.id.not_in(list(exclude_ids)))
        stmt = stmt.order_by(Media.id.desc() if order == "desc" else Media.id.asc()).limit(limit)
        async with self._session() as session:
            results = await session.execute(stmt)
            return [MediaMetadata.model_validate(media) for media in results.scalars().all()]

    async def count_missing(self) -> int:
        async with self._session() as session:
            stmt = select(func.count()).select_from(Media).where(self._not_indexed())
            return (await session.execute(stmt)).scalar_one()

    async def get_max_media_id(self) -> int | None:
        async with self._session() as session:
            return (await session.execute(select(func.max(Media.id)))).scalar_one()
