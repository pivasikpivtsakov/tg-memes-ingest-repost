import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from shared.db.models import MediaOcr
from shared.db.repositories.media_index import MediaIndexRepository


@dataclass(frozen=True)
class OcrRow:
    media_id: int
    text: str
    text_norm: str
    engine: str


@dataclass(frozen=True)
class OcrMatch:
    media_id: int
    score: float


class OcrRepository(MediaIndexRepository[OcrRow]):
    index_model = MediaOcr

    async def insert_many(self, rows: list[OcrRow]) -> int:
        if not rows:
            return 0
        stmt = insert(MediaOcr).values([
            {
                MediaOcr.media_id.key: row.media_id,
                MediaOcr.text.key: row.text,
                MediaOcr.text_norm.key: row.text_norm,
                MediaOcr.engine.key: row.engine,
            }
            for row in rows
        ]).on_conflict_do_nothing(
            index_elements=[MediaOcr.media_id],
        ).returning(MediaOcr.media_id)
        async with self._session() as session:
            result = await session.execute(stmt)
            return len(result.all())

    async def get_texts(self, media_ids: list[int]) -> dict[int, str]:
        if not media_ids:
            return {}
        async with self._session() as session:
            results = await session.execute(
                select(MediaOcr.media_id, MediaOcr.text).where(MediaOcr.media_id.in_(media_ids))
            )
            return {row.media_id: row.text for row in results}

    async def search_exact(self, query_norm: str, *, limit: int) -> list[OcrMatch]:
        """Whole phrase on word boundaries; memes where the phrase is most of the text rank first."""
        pattern = rf"\m{re.escape(query_norm)}\M"
        score = func.similarity(MediaOcr.text_norm, query_norm)
        stmt = (
            select(MediaOcr.media_id, score.label("score"))
            .where(MediaOcr.text_norm.regexp_match(pattern))
            .order_by(score.desc(), MediaOcr.media_id.desc())
            .limit(limit)
        )
        async with self._session() as session:
            results = await session.execute(stmt)
            return [OcrMatch(media_id=row.media_id, score=row.score) for row in results]

    async def search_trigram(
        self,
        query_norm: str,
        *,
        limit: int,
        threshold: float,
    ) -> list[OcrMatch]:
        """Fuzzy phrase match that tolerates OCR errors, typos and word forms."""
        score = func.word_similarity(query_norm, MediaOcr.text_norm)
        stmt = (
            select(MediaOcr.media_id, score.label("score"))
            .where(MediaOcr.text_norm.op("%>")(query_norm))
            .order_by(score.desc(), MediaOcr.media_id.desc())
            .limit(limit)
        )
        async with self._session() as session:
            await session.execute(
                select(func.set_config("pg_trgm.word_similarity_threshold", str(threshold), True))
            )
            results = await session.execute(stmt)
            return [OcrMatch(media_id=row.media_id, score=row.score) for row in results]
