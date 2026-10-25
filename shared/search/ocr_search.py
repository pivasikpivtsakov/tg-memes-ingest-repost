from shared.db.repositories import OcrMatch, OcrRepository
from shared.search.ranking import CANDIDATE_LIMIT

_TRIGRAM_THRESHOLD = 0.5


def _scores(matches: list[OcrMatch]) -> list[tuple[int, float]]:
    return [(match.media_id, match.score) for match in matches]


class OcrSearch:
    """Exact phrase and trigram matches over OCR text."""

    def __init__(self, ocr: OcrRepository) -> None:
        self._ocr = ocr

    async def exact(self, query_norm: str) -> list[tuple[int, float]]:
        return _scores(await self._ocr.search_exact(query_norm, limit=CANDIDATE_LIMIT))

    async def trigram(self, query_norm: str) -> list[tuple[int, float]]:
        matches = await self._ocr.search_trigram(
            query_norm,
            limit=CANDIDATE_LIMIT,
            threshold=_TRIGRAM_THRESHOLD,
        )
        return _scores(matches)

    async def get_texts(self, media_ids: list[int]) -> dict[int, str]:
        return await self._ocr.get_texts(media_ids)
