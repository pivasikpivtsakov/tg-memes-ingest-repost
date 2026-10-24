import asyncio
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from shared.db.repositories import ClipEmbeddingRepository, MediaRepository, OcrRepository
from shared.db.repositories.media import MediaMetadata
from shared.db.session import AsyncDatabaseManager
from shared.search.clip_text import ClipTextEncoder
from shared.search.text import normalize_text

Channel = Literal["exact", "trgm", "clip"]

_CHANNEL_LIMIT = 50
_RRF_K = 60
_TRIGRAM_THRESHOLD = 0.5
_HNSW_EF_SEARCH = 100

# Longer queries are usually a remembered phrase; one or two words more often name a template or scene.
_PHRASE_MIN_WORDS = 3
_PHRASE_WEIGHTS: dict[Channel, float] = {"exact": 1.0, "trgm": 1.0, "clip": 0.5}
_SHORT_WEIGHTS: dict[Channel, float] = {"exact": 1.0, "trgm": 0.6, "clip": 1.0}


@dataclass(frozen=True)
class ChannelMatch:
    rank: int
    score: float


@dataclass(frozen=True)
class SearchHit:
    media: MediaMetadata
    text: str | None
    score: float
    channels: dict[Channel, ChannelMatch]

    @property
    def exact(self) -> bool:
        return "exact" in self.channels


class SearchService:
    """Exact phrase matches first, then Reciprocal Rank Fusion of trigram and CLIP results."""

    def __init__(self, *, database_url: str, models_dir: Path) -> None:
        self._db = AsyncDatabaseManager(database_url)
        self._media = MediaRepository(self._db)
        self._ocr = OcrRepository(self._db)
        self._clip = ClipEmbeddingRepository(self._db)
        self._text_encoder = ClipTextEncoder(models_dir=models_dir)

    async def dispose(self) -> None:
        await self._db.dispose()

    async def search(self, query: str, *, limit: int = 20) -> list[SearchHit]:
        query_norm = normalize_text(query)
        if not query_norm:
            return []

        exact, trigram, query_embedding = await asyncio.gather(
            self._ocr.search_exact(query_norm, limit=_CHANNEL_LIMIT),
            self._ocr.search_trigram(query_norm, limit=_CHANNEL_LIMIT, threshold=_TRIGRAM_THRESHOLD),
            asyncio.to_thread(self._text_encoder.encode, query.strip()),
        )
        clip = await self._clip.nearest(query_embedding, limit=_CHANNEL_LIMIT, ef_search=_HNSW_EF_SEARCH)

        channels: dict[int, dict[Channel, ChannelMatch]] = defaultdict(dict)
        ranked: dict[Channel, list[tuple[int, float]]] = {
            "exact": [(match.media_id, match.score) for match in exact],
            "trgm": [(match.media_id, match.score) for match in trigram],
            "clip": [(match.media_id, 1.0 - match.distance) for match in clip],
        }
        for channel, matches in ranked.items():
            for rank, (media_id, score) in enumerate(matches, start=1):
                channels[media_id][channel] = ChannelMatch(rank=rank, score=score)

        weights = _PHRASE_WEIGHTS if len(query_norm.split()) >= _PHRASE_MIN_WORDS else _SHORT_WEIGHTS
        fused = {
            media_id: sum(weights[channel] / (_RRF_K + match.rank) for channel, match in matches.items())
            for media_id, matches in channels.items()
        }
        top_ids = sorted(
            fused,
            key=lambda media_id: ("exact" in channels[media_id], fused[media_id]),
            reverse=True,
        )[:limit]

        medias, texts = await asyncio.gather(
            self._media.list_by_ids(top_ids),
            self._ocr.get_texts(top_ids),
        )
        return [
            SearchHit(
                media=medias[media_id],
                text=texts.get(media_id),
                score=fused[media_id],
                channels=channels[media_id],
            )
            for media_id in top_ids
            if media_id in medias
        ]
