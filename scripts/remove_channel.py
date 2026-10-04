#!/usr/bin/env python3
"""Leave a Telegram channel and remove it from the ingestion allowlist."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from telethon import TelegramClient

from sender_tg_app.config import config
from shared.services import (
    ChannelTarget,
    ChannelTargetKind,
    leave_and_unallow,
    parse_channel_target,
    resolve_channel,
)
from shared.redis import AllowedChatsRepository, create_redis


async def leave_channel(raw_target: str) -> int:
    target = parse_channel_target(raw_target)
    if target is None:
        print(f"Could not parse channel target: {raw_target}")
        return 1

    redis = create_redis(config.redis_url)
    allowed_chats = AllowedChatsRepository(redis=redis)
    client = TelegramClient(config.session_name, config.api_id, config.api_hash)
    print(f"Connecting using session: {config.session_name}")
    try:
        async with client:
            chat_id = await _resolve_chat_id(
                client=client,
                allowed_chats=allowed_chats,
                target=target,
            )
            if chat_id is None:
                print(f"Channel not found in allowlist and could not be resolved: {raw_target}")
                return 1
            print(f"Leaving chat_id={chat_id}")
            result = await leave_and_unallow(client, allowed_chats, chat_id)
    except Exception as exc:
        print(f"Leave failed: {exc}")
        return 1
    finally:
        await redis.aclose()

    print(f"OK: removed {result.label} // {result.chat_id}")
    return 0


async def _resolve_chat_id(
    *,
    client: TelegramClient,
    allowed_chats: AllowedChatsRepository,
    target: ChannelTarget,
) -> int | None:
    if target.kind is ChannelTargetKind.ID:
        return int(target.value)

    stored = await allowed_chats.all()
    needle = target.value.lower()
    for chat_id, label in stored.items():
        if f"@{needle}" in label.lower() or needle in label.lower():
            return chat_id

    try:
        result = await resolve_channel(client, target)
    except Exception:
        return None
    return result.chat_id


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python remove_channel.py <channel_username_or_link>")
        print("\nExample:")
        print("  python remove_channel.py @mychannel")
        sys.exit(1)
    sys.exit(asyncio.run(leave_channel(sys.argv[1])))


if __name__ == "__main__":
    main()
