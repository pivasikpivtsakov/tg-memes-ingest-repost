from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from shared.db import AsyncDatabaseManager, Media
from shared.storage import MediaMetadata

_POSTED_AT_BEFORE = timedelta(seconds=5)
_POSTED_AT_AFTER = timedelta(seconds=40)


def _as_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class MediaLookup:
    def __init__(self, *, database_url: str) -> None:
        self._db = AsyncDatabaseManager(database_url)

    async def get_by_posted_at(self, posted_at: datetime) -> MediaMetadata | None:
        target = _as_naive_utc(posted_at)
        start = target - _POSTED_AT_BEFORE
        end = target + _POSTED_AT_AFTER
        async with self._db.get_session() as session:
            result = await session.execute(
                select(Media).where(
                    Media.posted_at_tg >= start,
                    Media.posted_at_tg <= end,
                )
            )
            candidates = result.scalars().all()
        if not candidates:
            return None
        media = min(
            candidates,
            key=lambda item: abs((item.posted_at_tg - target).total_seconds()),
        )
        return MediaMetadata.model_validate(media)

    async def dispose(self) -> None:
        await self._db.dispose()
