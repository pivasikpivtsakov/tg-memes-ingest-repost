from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.session import AsyncDatabaseManager


class PostgresRepository:
    def __init__(self, db: AsyncDatabaseManager) -> None:
        self._db = db

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        async with self._db.get_session() as session:
            yield session
