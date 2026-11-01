#!/usr/bin/env python3
"""Recover posted_message_id of sent memes by matching posted_at_tg to target channel post dates."""
import argparse
import asyncio
import bisect
import logging
import statistics
import sys
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from operator import attrgetter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from telethon import TelegramClient
from telethon.tl.types import Message

from sender_tg_app.config import config
from shared.db.models import MediaType
from shared.db.repositories.media import MediaMetadata, MediaRepository
from shared.db.session import AsyncDatabaseManager
from shared.logger import setup_logging

_BATCH_SIZE = 100


@dataclass(frozen=True)
class _Post:
    message_id: int
    media_type: MediaType
    posted_at: datetime


@dataclass(frozen=True)
class _Pending:
    media: MediaMetadata
    posted_at: datetime


@dataclass(frozen=True)
class _Batch:
    posts: list[_Post]
    scanned: int
    fetched_until: datetime


def _to_db_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _media_type_of(message: Message) -> MediaType | None:
    if message.photo is not None:
        return MediaType.PHOTO
    if message.document is not None:
        return MediaType.VIDEO
    return None


async def _iter_batches(
    *,
    client: TelegramClient,
    chat_id: int,
    start: datetime,
    end: datetime,
) -> AsyncIterator[_Batch]:
    entity = await client.get_entity(chat_id)
    posts: list[_Post] = []
    scanned = 0
    messages = client.iter_messages(entity, reverse=True, offset_date=start.replace(tzinfo=UTC))
    async for message in messages:
        posted_at = _to_db_time(message.date)
        if posted_at > end:
            break
        scanned += 1
        media_type = _media_type_of(message)
        if media_type is not None:
            posts.append(_Post(message_id=message.id, media_type=media_type, posted_at=posted_at))
        if scanned == _BATCH_SIZE:
            yield _Batch(posts=posts, scanned=scanned, fetched_until=posted_at)
            posts = []
            scanned = 0
    yield _Batch(posts=posts, scanned=scanned, fetched_until=end)


def _match(
    *,
    pending: Sequence[_Pending],
    posts: Sequence[_Post],
    taken_message_ids: set[int],
    max_lag: timedelta,
    max_lead: timedelta,
) -> dict[int, _Post]:
    posts = sorted(posts, key=attrgetter("posted_at"))
    post_dates = [post.posted_at for post in posts]
    pairs: list[tuple[timedelta, int, int, _Pending, _Post]] = []
    for rank, item in enumerate(pending):
        low = bisect.bisect_left(post_dates, item.posted_at - max_lag)
        high = bisect.bisect_right(post_dates, item.posted_at + max_lead)
        for post in posts[low:high]:
            if post.media_type == item.media.media_type and post.message_id not in taken_message_ids:
                cost = abs(item.posted_at - post.posted_at)
                pairs.append((cost, rank, post.message_id, item, post))
    pairs.sort(key=lambda pair: pair[:3])

    matched: dict[int, _Post] = {}
    used_message_ids = set(taken_message_ids)
    for _, _, message_id, item, post in pairs:
        if item.media.id in matched or message_id in used_message_ids:
            continue
        matched[item.media.id] = post
        used_message_ids.add(message_id)
    return matched


class _StreamMatcher:
    def __init__(
        self,
        *,
        pending: Sequence[_Pending],
        taken_message_ids: set[int],
        max_lag: timedelta,
        max_lead: timedelta,
    ) -> None:
        self._pending = pending
        self._dates = [item.posted_at for item in pending]
        self._taken = set(taken_message_ids)
        self._max_lag = max_lag
        self._max_lead = max_lead
        self._posts: list[_Post] = []
        self._settled = 0
        self.lags: list[float] = []
        self.unmatched_ids: list[int] = []

    def feed(self, *, posts: Sequence[_Post], fetched_until: datetime) -> dict[int, int]:
        self._posts.extend(posts)
        return self._settle(
            cutoff=bisect.bisect_right(self._dates, fetched_until - self._max_lag - 2 * self._max_lead),
            horizon=bisect.bisect_right(self._dates, fetched_until + self._max_lag),
        )

    def finish(self) -> dict[int, int]:
        return self._settle(cutoff=len(self._pending), horizon=len(self._pending))

    def _settle(self, *, cutoff: int, horizon: int) -> dict[int, int]:
        if cutoff <= self._settled:
            return {}
        matched = _match(
            pending=self._pending[self._settled:horizon],
            posts=self._posts,
            taken_message_ids=self._taken,
            max_lag=self._max_lag,
            max_lead=self._max_lead,
        )
        result: dict[int, int] = {}
        for item in self._pending[self._settled:cutoff]:
            post = matched.get(item.media.id)
            if post is None:
                self.unmatched_ids.append(item.media.id)
                continue
            result[item.media.id] = post.message_id
            self._taken.add(post.message_id)
            self.lags.append((item.posted_at - post.posted_at).total_seconds())
        self._settled = cutoff
        if cutoff < len(self._pending):
            window_start = self._pending[cutoff].posted_at - self._max_lag
            self._posts = [
                post
                for post in self._posts
                if post.posted_at >= window_start and post.message_id not in self._taken
            ]
        return result


def _print_progress(*, done: float, scanned: int, found: int, written: int) -> None:
    print(
        f"\rFetching channel: {done:.0%}, {scanned} messages scanned, {found} media posts, {written} written",
        end="",
        flush=True,
    )


def _print_summary(*, pending_count: int, found: int, matcher: _StreamMatcher) -> None:
    print(f"{pending_count} memes had posted_at_tg but no posted_message_id")
    print(f"{found} media posts found in the channel for that period")
    print(f"Written: {len(matcher.lags)}, unmatched: {len(matcher.unmatched_ids)}")
    if matcher.lags:
        print(
            f"posted_at_tg minus post date, seconds: min {min(matcher.lags):.1f}, "
            f"median {statistics.median(matcher.lags):.1f}, max {max(matcher.lags):.1f}"
        )
    if matcher.unmatched_ids:
        print(f"Unmatched media ids: {', '.join(map(str, matcher.unmatched_ids))}")


async def main(*, chat_id: int, max_lag: timedelta, max_lead: timedelta) -> int:
    db = AsyncDatabaseManager(config.database_url)
    repo = MediaRepository(db)
    try:
        medias = await repo.list_posted_tg()
        pending = [
            _Pending(media=media, posted_at=media.posted_at_tg)
            for media in medias
            if media.posted_at_tg is not None and media.posted_message_id is None
        ]
        if not pending:
            print("Nothing to backfill.")
            return 0
        matcher = _StreamMatcher(
            pending=pending,
            taken_message_ids={
                media.posted_message_id for media in medias if media.posted_message_id is not None
            },
            max_lag=max_lag,
            max_lead=max_lead,
        )
        start = pending[0].posted_at - max_lag
        end = pending[-1].posted_at + max_lead
        span = max((end - start).total_seconds(), 1.0)
        scanned = 0
        found = 0
        written = 0

        client = TelegramClient(config.session_name, config.api_id, config.api_hash)
        async with client:
            async for batch in _iter_batches(client=client, chat_id=chat_id, start=start, end=end):
                scanned += batch.scanned
                found += len(batch.posts)
                matched = matcher.feed(posts=batch.posts, fetched_until=batch.fetched_until)
                await repo.set_posted_message_ids(matched)
                written += len(matched)
                _print_progress(
                    done=(batch.fetched_until - start).total_seconds() / span,
                    scanned=scanned,
                    found=found,
                    written=written,
                )

        matched = matcher.finish()
        await repo.set_posted_message_ids(matched)
        written += len(matched)
        _print_progress(done=1.0, scanned=scanned, found=found, written=written)
        print()
        _print_summary(pending_count=len(pending), found=found, matcher=matcher)
        return 0
    finally:
        await db.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chat", type=int, default=int(config.target_chat_id))
    parser.add_argument(
        "--max-lag",
        type=float,
        default=40,
        help="seconds posted_at_tg may trail the channel post",
    )
    parser.add_argument(
        "--max-lead",
        type=float,
        default=5,
        help="seconds posted_at_tg may precede the channel post (clock skew)",
    )
    args = parser.parse_args()
    setup_logging(logging.WARNING)
    sys.exit(asyncio.run(main(
        chat_id=args.chat,
        max_lag=timedelta(seconds=args.max_lag),
        max_lead=timedelta(seconds=args.max_lead),
    )))
