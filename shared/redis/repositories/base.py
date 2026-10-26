from collections.abc import Iterable, Mapping

from redis.asyncio import Redis


def _as_text(value: str | bytes) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return value


class RedisRepository:
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    @staticmethod
    def _int_or_none(value: str | bytes | None) -> int | None:
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def _int_set(values: Iterable[str | bytes]) -> frozenset[int]:
        return frozenset(int(value) for value in values)

    @staticmethod
    def _int_keyed(entries: Mapping[str | bytes, str | bytes]) -> dict[int, str]:
        return {int(key): _as_text(value) for key, value in entries.items()}
