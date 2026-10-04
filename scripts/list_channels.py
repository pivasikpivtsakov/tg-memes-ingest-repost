#!/usr/bin/env python3
"""List allowed ingestion channels from Redis."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion_app.config import config
from shared.redis import AllowedChatsRepository, create_redis


async def main() -> None:
    redis = create_redis(config.redis_url)
    allowed_chats = AllowedChatsRepository(redis=redis)
    try:
        stored_chats = await allowed_chats.all()
    finally:
        await redis.aclose()

    print(f"Found {len(stored_chats)} channels in Redis allowed_chats")
    print("=" * 70)
    for idx, (chat_id, label) in enumerate(stored_chats.items(), 1):
        print(f"{idx}. {label}")
        print(f"   ID: {chat_id}")
        print()
    print("=" * 70)
    print(f"Total: {len(stored_chats)} channels")


if __name__ == "__main__":
    asyncio.run(main())
