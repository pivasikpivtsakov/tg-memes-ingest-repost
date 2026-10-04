#!/usr/bin/env python3
"""Join a Telegram channel and add it to the ingestion allowlist."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from telethon import TelegramClient

from sender_tg_app.config import config
from shared.services import join_and_allow, parse_channel_target
from shared.redis import AllowedChatsRepository, create_redis


async def join_channel(raw_target: str) -> int:
    target = parse_channel_target(raw_target)
    if target is None:
        print(f"Could not parse channel target: {raw_target}")
        print("Expected @username, t.me link, invite link, or -100... id")
        return 1

    redis = create_redis(config.redis_url)
    allowed_chats = AllowedChatsRepository(redis=redis)
    client = TelegramClient(config.session_name, config.api_id, config.api_hash)
    print(f"Connecting using session: {config.session_name}")
    print(f"Joining {target.kind.value}: {target.value}")
    try:
        async with client:
            result = await join_and_allow(client, allowed_chats, target)
    except Exception as exc:
        print(f"Join failed: {exc}")
        return 1
    finally:
        await redis.aclose()

    status = "already a member" if result.already_member else "joined"
    print(f"OK ({status}): {result.label} // {result.chat_id}")
    return 0


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python join_channel.py <channel_username_or_link>")
        print("\nExample:")
        print("  python join_channel.py @mychannel")
        print("  python join_channel.py https://t.me/+inviteHash")
        sys.exit(1)
    sys.exit(asyncio.run(join_channel(sys.argv[1])))


if __name__ == "__main__":
    main()
