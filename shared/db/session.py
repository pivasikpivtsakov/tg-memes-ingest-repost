"""
Async SQLAlchemy session management. Does not migrate schema.
"""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def to_async_database_url(database_url: str) -> str:
    if "+psycopg_async://" in database_url:
        return database_url
    return database_url.replace("postgresql+psycopg://", "postgresql+psycopg_async://", 1)


class AsyncDatabaseManager:
    """Async SQLAlchemy engine and session factory. Does not migrate schema."""

    def __init__(self, database_url: str):
        self.database_url = to_async_database_url(database_url)
        self.engine = create_async_engine(
            self.database_url,
            pool_pre_ping=True,
            echo=False,
        )
        self.SessionLocal = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            autoflush=False,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession]:
        session = self.SessionLocal()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def dispose(self) -> None:
        await self.engine.dispose()
