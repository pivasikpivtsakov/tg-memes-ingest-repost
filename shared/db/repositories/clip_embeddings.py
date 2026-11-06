from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from shared.db.models import Media, MediaClipEmbedding, MediaType
from shared.db.repositories.media_index import MediaIndexRepository

# Annotation only. pgvector serializes the array, so this module does not import numpy.
if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True)
class ClipEmbeddingRow:
    media_id: int
    embedding: np.ndarray
    model: str
    frame_count: int


@dataclass(frozen=True)
class ClipMatch:
    media_id: int
    distance: float


@dataclass(frozen=True)
class StoredClipEmbedding:
    media_id: int
    embedding: list[float]


class ClipEmbeddingRepository(MediaIndexRepository[ClipEmbeddingRow]):
    index_model = MediaClipEmbedding

    async def insert_many(self, rows: list[ClipEmbeddingRow]) -> int:
        if not rows:
            return 0
        stmt = insert(MediaClipEmbedding).values([
            {
                MediaClipEmbedding.media_id.key: row.media_id,
                MediaClipEmbedding.embedding.key: row.embedding,
                MediaClipEmbedding.model.key: row.model,
                MediaClipEmbedding.frame_count.key: row.frame_count,
            }
            for row in rows
        ]).on_conflict_do_nothing(
            index_elements=[MediaClipEmbedding.media_id],
        ).returning(MediaClipEmbedding.media_id)
        async with self._session() as session:
            result = await session.execute(stmt)
            return len(result.all())

    async def iter_by_media_type(
        self,
        media_type: MediaType,
        *,
        batch_size: int,
    ) -> AsyncIterator[list[StoredClipEmbedding]]:
        stmt = (
            select(MediaClipEmbedding.media_id, MediaClipEmbedding.embedding)
            .join(Media, Media.id == MediaClipEmbedding.media_id)
            .where(Media.media_type == media_type)
            .execution_options(yield_per=batch_size)
        )
        async with self._session() as session:
            results = await session.stream(stmt)
            async for rows in results.partitions():
                yield [StoredClipEmbedding(media_id=row.media_id, embedding=row.embedding) for row in rows]

    async def nearest(self, query: np.ndarray, *, limit: int, ef_search: int) -> list[ClipMatch]:
        distance = MediaClipEmbedding.embedding.cosine_distance(query)
        stmt = (
            select(MediaClipEmbedding.media_id, distance.label("distance"))
            .order_by(distance)
            .limit(limit)
        )
        async with self._session() as session:
            # HNSW returns at most ef_search rows, so it must cover the limit.
            await session.execute(select(func.set_config("hnsw.ef_search", str(ef_search), True)))
            results = await session.execute(stmt)
            return [ClipMatch(media_id=row.media_id, distance=row.distance) for row in results]
