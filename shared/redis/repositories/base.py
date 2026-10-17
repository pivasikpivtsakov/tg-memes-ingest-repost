from collections.abc import Iterable, Mapping

from redis.asyncio import Redis


class RedisRepository:
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    @staticmethod
    def _int_or_none(value: str | None) -> int | None:
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def _int_set(values: Iterable[str]) -> frozenset[int]:
        return frozenset(int(value) for value in values)

    @staticmethod
    def _int_keyed(entries: Mapping[str, str]) -> dict[int, str]:
        return {int(key): value for key, value in entries.items()}
