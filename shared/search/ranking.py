from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum


class Channel(StrEnum):
    EXACT = "exact"
    TRGM = "trgm"
    CLIP = "clip"


# Each channel returns this many candidates; fusion only reorders them.
CANDIDATE_LIMIT = 50

_RRF_K = 60

# Longer queries are usually a remembered phrase; one or two words more often name a template or scene.
_PHRASE_MIN_WORDS = 3
_PHRASE_WEIGHTS: dict[Channel, float] = {
    Channel.EXACT: 1.0,
    Channel.TRGM: 1.0,
    Channel.CLIP: 0.5,
}
_SHORT_WEIGHTS: dict[Channel, float] = {
    Channel.EXACT: 1.0,
    Channel.TRGM: 0.6,
    Channel.CLIP: 1.0,
}


@dataclass(frozen=True)
class ChannelMatch:
    rank: int
    score: float


@dataclass(frozen=True)
class FusedHit:
    media_id: int
    score: float
    channels: dict[Channel, ChannelMatch]


def fuse(
    *,
    exact: list[tuple[int, float]],
    trigram: list[tuple[int, float]],
    clip: list[tuple[int, float]],
    query_norm: str,
    limit: int,
) -> list[FusedHit]:
    """Reciprocal Rank Fusion. Exact hits sort ahead of the fused score."""
    grouped: dict[int, dict[Channel, ChannelMatch]] = defaultdict(dict)
    ranked: dict[Channel, list[tuple[int, float]]] = {
        Channel.EXACT: exact,
        Channel.TRGM: trigram,
        Channel.CLIP: clip,
    }
    for channel, matches in ranked.items():
        for rank, (media_id, score) in enumerate(matches, start=1):
            grouped[media_id][channel] = ChannelMatch(rank=rank, score=score)

    weights = _PHRASE_WEIGHTS if len(query_norm.split()) >= _PHRASE_MIN_WORDS else _SHORT_WEIGHTS
    scored = {
        media_id: sum(weights[channel] / (_RRF_K + match.rank) for channel, match in matches.items())
        for media_id, matches in grouped.items()
    }
    chosen = sorted(
        scored,
        key=lambda media_id: (Channel.EXACT in grouped[media_id], scored[media_id]),
        reverse=True,
    )[:limit]
    return [
        FusedHit(media_id=media_id, score=scored[media_id], channels=grouped[media_id])
        for media_id in chosen
    ]
