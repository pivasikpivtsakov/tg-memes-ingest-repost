from datetime import datetime, timedelta, timezone

from shared.db.repositories.media import MediaMetadata, MediaRepository
from shared.db.session import AsyncDatabaseManager

_POSTED_AT_BEFORE = timedelta(seconds=5)
_POSTED_AT_AFTER = timedelta(seconds=40)


def _as_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class MediaLookup:
    def __init__(self, *, database_url: str) -> None:
        self._db = AsyncDatabaseManager(database_url)
        self._repo = MediaRepository(self._db)

    async def get_by_posted_at(self, posted_at: datetime) -> MediaMetadata | None:
        target = _as_naive_utc(posted_at)
        candidates = await self._repo.list_by_posted_at_range(
            start=target - _POSTED_AT_BEFORE,
            end=target + _POSTED_AT_AFTER,
        )
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda item: abs((item.posted_at_tg - target).total_seconds()),
        )

    async def dispose(self) -> None:
        await self._db.dispose()
