import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from shared.db.repositories import ClipEmbeddingRepository
from shared.device import DeviceChoice
from shared.search.clip_text import ClipTextEncoder
from shared.search.ranking import CANDIDATE_LIMIT

# HNSW returns at most ef_search rows. Twice the candidate limit, same ratio as the old 100/50 pair,
# otherwise the tail of the window is whatever the index walked first.
_HNSW_EF_SEARCH = 200


class ClipSearch:
    """Nearest meme images for a text query. Score is cosine similarity (1 - distance)."""

    def __init__(
        self,
        embeddings: ClipEmbeddingRepository,
        *,
        models_dir: Path,
        device: DeviceChoice,
    ) -> None:
        self._embeddings = embeddings
        self._encoder = ClipTextEncoder(models_dir=models_dir, device=device)
        # Parallel forward passes fight over the GIL and share one CUDA stream: two threads are slower than one.
        self._encode_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clip-text")

    def load(self) -> None:
        self._encoder.load()

    def close(self) -> None:
        self._encode_executor.shutdown()

    async def encode(self, query: str) -> np.ndarray:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._encode_executor, self._encoder.encode, query.strip())

    async def nearest(self, embedding: np.ndarray) -> list[tuple[int, float]]:
        matches = await self._embeddings.nearest(
            embedding,
            limit=CANDIDATE_LIMIT,
            ef_search=_HNSW_EF_SEARCH,
        )
        return [(match.media_id, 1.0 - match.distance) for match in matches]
