#!/usr/bin/env python3
"""
Seed the Redis allowed-chats hash from config.json.

Reads allowed_chat_ids together with their inline `// name (@user)` comments
straight from the raw config.json text (json5 discards comments), then writes
each id -> label pair into Redis. Idempotent / re-runnable.
"""
import asyncio
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion_app.config import config
from shared.logger import setup_logging
from shared.redis import AllowedChatsRepository, create_redis

logger = logging.getLogger(__name__)

_ALLOWED_BLOCK_RE = re.compile(r'"allowed_chat_ids"\s*:\s*\[(.*?)\]', re.DOTALL)
_ENTRY_RE = re.compile(r'\s*(-?\d+)\s*,?\s*(?://\s*(.*?))?\s*$')


def parse_allowed_chats(config_text: str) -> list[tuple[int, str]]:
    block_match = _ALLOWED_BLOCK_RE.search(config_text)
    if not block_match:
        return []

    entries: list[tuple[int, str]] = []
    for line in block_match.group(1).splitlines():
        entry_match = _ENTRY_RE.match(line)
        if not entry_match:
            continue
        chat_id = int(entry_match.group(1))
        label = (entry_match.group(2) or "").strip()
        entries.append((chat_id, label))
    return entries


async def main() -> None:
    setup_logging()

    config_path = Path(__file__).parent.parent / 'config.json'
    entries = parse_allowed_chats(config_path.read_text())
    logger.info("parsed %d allowed chats from config.json", len(entries))

    redis = create_redis(config.redis_url)
    repo = AllowedChatsRepository(redis=redis)
    try:
        for chat_id, label in entries:
            await repo.add(chat_id=chat_id, label=label)
            logger.info("seeded chat_id=%d label=%s", chat_id, label)
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
