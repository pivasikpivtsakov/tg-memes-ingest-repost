from redis.asyncio import Redis
from telethon import TelegramClient

from shared.redis.repositories import AllowedChatsRepository
from shared.services.channels import (
    ChannelResult,
    ChannelTarget,
    join_and_allow as join_channel,
    leave_and_unallow as leave_channel,
    refresh_allowed_chat_labels as refresh_channel_labels,
)


class AllowedChatsService:
    def __init__(self, *, redis: Redis) -> None:
        self._repo = AllowedChatsRepository(redis=redis)

    async def is_allowed(self, *, chat_id: int) -> bool:
        return await self._repo.is_allowed(chat_id=chat_id)

    async def all(self) -> dict[int, str]:
        return await self._repo.all()

    async def join_and_allow(
        self,
        client: TelegramClient,
        target: ChannelTarget,
    ) -> ChannelResult:
        return await join_channel(client, self._repo, target)

    async def leave_and_unallow(
        self,
        client: TelegramClient,
        chat_id: int,
    ) -> ChannelResult:
        return await leave_channel(client, self._repo, chat_id)

    async def refresh_allowed_chat_labels(self, client: TelegramClient) -> None:
        await refresh_channel_labels(client, self._repo)
