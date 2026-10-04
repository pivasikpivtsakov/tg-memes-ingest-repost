from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from shared.db import DatabaseManager, Media
from shared.storage import MediaMetadata

_POSTED_AT_WINDOW = timedelta(seconds=35)


def _as_naive_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().replace(tzinfo=None)


class MediaLookup:
    def __init__(self, *, database_url: str) -> None:
        self._db = DatabaseManager(database_url)
        self._db.init_db()

    def get_by_posted_at(self, posted_at: datetime) -> MediaMetadata | None:
        start = _as_naive_local(posted_at)
        end = start + _POSTED_AT_WINDOW
        with self._db.get_session() as session:
            media = session.execute(
                select(Media)
                .where(
                    Media.posted_at_tg >= start,
                    Media.posted_at_tg <= end,
                )
                .order_by(Media.posted_at_tg.asc())
                .limit(1)
            ).scalar_one_or_none()
            if media is None:
                return None
            return MediaMetadata.model_validate(media)
