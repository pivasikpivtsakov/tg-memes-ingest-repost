from redis.asyncio import Redis

from shared.redis.repositories import AdminIdsRepository


class AdminsService:
    def __init__(self, *, redis: Redis) -> None:
        self._repo = AdminIdsRepository(redis=redis)

    async def super_id(self) -> int | None:
        return await self._repo.super_id()

    async def is_super(self, *, user_id: int) -> bool:
        return await self._repo.is_super(user_id=user_id)

    async def all(self) -> frozenset[int]:
        return await self._repo.all()

    async def contains(self, *, user_id: int) -> bool:
        return await self._repo.contains(user_id=user_id)

    async def add(self, *, user_id: int) -> None:
        await self._repo.add(user_id=user_id)

    async def remove(self, *, user_id: int) -> None:
        await self._repo.remove(user_id=user_id)
