from redis.asyncio import Redis

_ADMINS_KEY = "admin_bot:admin_ids"
_SUPER_KEY = "admin_bot:super_admin_id"


class AdminIdsRepository:
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    async def super_id(self) -> int | None:
        value = await self._redis.get(_SUPER_KEY)
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    async def is_super(self, *, user_id: int) -> bool:
        stored = await self.super_id()
        return stored is not None and stored == user_id

    async def all(self) -> frozenset[int]:
        members = await self._redis.smembers(_ADMINS_KEY)
        return frozenset(int(member) for member in members)

    async def contains(self, *, user_id: int) -> bool:
        return bool(await self._redis.sismember(_ADMINS_KEY, str(user_id)))

    async def add(self, *, user_id: int) -> None:
        await self._redis.sadd(_ADMINS_KEY, str(user_id))

    async def remove(self, *, user_id: int) -> None:
        await self._redis.srem(_ADMINS_KEY, str(user_id))
