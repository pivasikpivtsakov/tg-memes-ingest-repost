#!/usr/bin/env python3
"""Recover posted_message_id of sent memes by matching posted_at_tg to target channel post dates."""
import argparse
import asyncio
import bisect
import logging
import statistics
import sys
from collections.abc import Sequence
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


@dataclass(frozen=True)
class _Post:
    message_id: int
    media_type: MediaType
    posted_at: datetime


@dataclass(frozen=True)
class _Pending:
    media: MediaMetadata
    posted_at: datetime


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


async def _fetch_posts(
    *,
    client: TelegramClient,
    chat_id: int,
    start: datetime,
    end: datetime,
) -> list[_Post]:
    entity = await client.get_entity(chat_id)
    posts: list[_Post] = []
    messages = client.iter_messages(entity, reverse=True, offset_date=start.replace(tzinfo=UTC))
    async for message in messages:
        posted_at = _to_db_time(message.date)
        if posted_at > end:
            break
        media_type = _media_type_of(message)
        if media_type is not None:
            posts.append(_Post(message_id=message.id, media_type=media_type, posted_at=posted_at))
    return posts


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


def _print_summary(*, pending: Sequence[_Pending], posts: Sequence[_Post], matched: dict[int, _Post]) -> None:
    print(f"{len(pending)} memes have posted_at_tg but no posted_message_id")
    print(f"{len(posts)} media posts found in the channel for that period")
    print(f"Matched: {len(matched)}, unmatched: {len(pending) - len(matched)}")
    lags = [
        (item.posted_at - matched[item.media.id].posted_at).total_seconds()
        for item in pending
        if item.media.id in matched
    ]
    if lags:
        print(
            f"posted_at_tg minus post date, seconds: min {min(lags):.1f}, "
            f"median {statistics.median(lags):.1f}, max {max(lags):.1f}"
        )
    unmatched_ids = [item.media.id for item in pending if item.media.id not in matched]
    if unmatched_ids:
        print(f"Unmatched media ids: {', '.join(map(str, unmatched_ids))}")


def _confirm(count: int) -> bool:
    answer = input(f"Write {count} posted_message_id values? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


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
        taken_message_ids = {
            media.posted_message_id for media in medias if media.posted_message_id is not None
        }

        client = TelegramClient(config.session_name, config.api_id, config.api_hash)
        async with client:
            posts = await _fetch_posts(
                client=client,
                chat_id=chat_id,
                start=pending[0].posted_at - max_lag,
                end=pending[-1].posted_at + max_lead,
            )

        matched = _match(
            pending=pending,
            posts=posts,
            taken_message_ids=taken_message_ids,
            max_lag=max_lag,
            max_lead=max_lead,
        )
        _print_summary(pending=pending, posts=posts, matched=matched)
        if not matched or not _confirm(len(matched)):
            return 0

        await repo.set_posted_message_ids(
            {media_id: post.message_id for media_id, post in matched.items()}
        )
        print("Done.")
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
