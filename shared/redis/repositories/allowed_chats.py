from shared.redis.repositories.base import RedisRepository

_KEY = "ingestion:allowed_chats"


class AllowedChatsRepository(RedisRepository):
    async def is_allowed(self, *, chat_id: int) -> bool:
        return await self._redis.hexists(_KEY, str(chat_id))

    async def add(self, *, chat_id: int, label: str) -> None:
        await self._redis.hset(_KEY, str(chat_id), label)

    async def remove(self, *, chat_id: int) -> None:
        await self._redis.hdel(_KEY, str(chat_id))

    async def all(self) -> dict[int, str]:
        return self._int_keyed(await self._redis.hgetall(_KEY))
