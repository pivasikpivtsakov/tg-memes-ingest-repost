import asyncio
from pathlib import Path

import numpy as np

from shared.db.repositories import ClipEmbeddingRepository
from shared.search.clip_text import ClipTextEncoder
from shared.search.ranking import CANDIDATE_LIMIT

# HNSW returns at most ef_search rows, so this stays above the candidate limit.
_HNSW_EF_SEARCH = 100


class ClipSearch:
    """Nearest meme images for a text query. Score is cosine similarity (1 - distance)."""

    def __init__(self, embeddings: ClipEmbeddingRepository, *, models_dir: Path) -> None:
        self._embeddings = embeddings
        self._encoder = ClipTextEncoder(models_dir=models_dir)

    async def encode(self, query: str) -> np.ndarray:
        return await asyncio.to_thread(self._encoder.encode, query.strip())

    async def nearest(self, embedding: np.ndarray) -> list[tuple[int, float]]:
        matches = await self._embeddings.nearest(
            embedding,
            limit=CANDIDATE_LIMIT,
            ef_search=_HNSW_EF_SEARCH,
        )
        return [(match.media_id, 1.0 - match.distance) for match in matches]
