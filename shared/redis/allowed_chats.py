from redis.asyncio import Redis

_KEY = "ingestion:allowed_chats"


class AllowedChatsRepository:
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    async def is_allowed(self, *, chat_id: int) -> bool:
        return await self._redis.hexists(_KEY, str(chat_id))

    async def add(self, *, chat_id: int, label: str) -> None:
        await self._redis.hset(_KEY, str(chat_id), label)

    async def remove(self, *, chat_id: int) -> None:
        await self._redis.hdel(_KEY, str(chat_id))

    async def all(self) -> dict[int, str]:
        entries = await self._redis.hgetall(_KEY)
        return {int(chat_id): label for chat_id, label in entries.items()}
