import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from shared.db.repositories import ClipEmbeddingRepository, MediaRepository, OcrRepository
from shared.db.repositories.media import MediaMetadata
from shared.db.session import AsyncDatabaseManager
from shared.device import DeviceChoice
from shared.search.clip_search import ClipSearch
from shared.search.ocr_search import OcrSearch
from shared.search.ranking import Channel, ChannelMatch, fuse
from shared.search.text import normalize_text


@dataclass(frozen=True)
class SearchTimings:
    """Wall time of one search. exact, trigram and encode run together."""

    total: float
    parallel: float
    exact: float
    trigram: float
    encode: float
    clip: float
    hydrate: float


@dataclass(frozen=True)
class SearchHit:
    media: MediaMetadata
    text: str | None
    score: float
    channels: dict[Channel, ChannelMatch]

    @property
    def exact(self) -> bool:
        return Channel.EXACT in self.channels


class _StageClock:
    def __init__(self) -> None:
        self.elapsed: dict[str, float] = {}

    async def measure[T](self, name: str, awaitable: Awaitable[T]) -> T:
        started = perf_counter()
        try:
            return await awaitable
        finally:
            self.elapsed[name] = perf_counter() - started


class SearchService:
    """Phrase queries keep exact OCR hits first. Fusion weights OCR above CLIP."""

    def __init__(
        self,
        *,
        db: AsyncDatabaseManager,
        models_dir: Path,
        device: DeviceChoice,
    ) -> None:
        self._media = MediaRepository(db)
        self._ocr = OcrSearch(OcrRepository(db))
        self._clip = ClipSearch(
            ClipEmbeddingRepository(db),
            models_dir=models_dir,
            device=device,
        )

    def load(self) -> None:
        self._clip.load()

    async def search(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> tuple[list[SearchHit], SearchTimings]:
        started = perf_counter()
        query_norm = normalize_text(query)
        if not query_norm:
            timings = SearchTimings(
                total=0, parallel=0, exact=0, trigram=0, encode=0, clip=0, hydrate=0,
            )
            return [], timings

        clock = _StageClock()
        exact, trigram, embedding = await clock.measure(
            "parallel",
            asyncio.gather(
                clock.measure("exact", self._ocr.exact(query_norm)),
                clock.measure("trigram", self._ocr.trigram(query_norm)),
                clock.measure("encode", self._clip.encode(query)),
            ),
        )
        clip = await clock.measure("clip", self._clip.nearest(embedding))
        fused = fuse(exact=exact, trigram=trigram, clip=clip, query_norm=query_norm, limit=limit)
        media_ids = [hit.media_id for hit in fused]
        medias, texts = await clock.measure(
            "hydrate",
            asyncio.gather(
                self._media.list_by_ids(media_ids),
                self._ocr.get_texts(media_ids),
            ),
        )
        timings = SearchTimings(
            total=perf_counter() - started,
            parallel=clock.elapsed["parallel"],
            exact=clock.elapsed["exact"],
            trigram=clock.elapsed["trigram"],
            encode=clock.elapsed["encode"],
            clip=clock.elapsed["clip"],
            hydrate=clock.elapsed["hydrate"],
        )
        hits = [
            SearchHit(
                media=medias[hit.media_id],
                text=texts.get(hit.media_id),
                score=hit.score,
                channels=hit.channels,
            )
            for hit in fused
            if hit.media_id in medias
        ]
        return hits, timings
