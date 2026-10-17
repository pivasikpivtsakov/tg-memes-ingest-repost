from shared.redis.repositories.base import RedisRepository

_ADMINS_KEY = "admin_bot:admin_ids"
_SUPER_KEY = "admin_bot:super_admin_id"


class AdminIdsRepository(RedisRepository):
    async def super_id(self) -> int | None:
        return self._int_or_none(await self._redis.get(_SUPER_KEY))

    async def is_super(self, *, user_id: int) -> bool:
        stored = await self.super_id()
        return stored is not None and stored == user_id

    async def all(self) -> frozenset[int]:
        return self._int_set(await self._redis.smembers(_ADMINS_KEY))

    async def contains(self, *, user_id: int) -> bool:
        return bool(await self._redis.sismember(_ADMINS_KEY, str(user_id)))

    async def add(self, *, user_id: int) -> None:
        await self._redis.sadd(_ADMINS_KEY, str(user_id))

    async def remove(self, *, user_id: int) -> None:
        await self._redis.srem(_ADMINS_KEY, str(user_id))
