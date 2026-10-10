"""
SQLAlchemy session management and database initialization.
"""
import logging
from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from shared.db.base import Base

logger = logging.getLogger(__name__)


def to_async_database_url(database_url: str) -> str:
    if "+psycopg_async://" in database_url:
        return database_url
    return database_url.replace("postgresql+psycopg://", "postgresql+psycopg_async://", 1)


class DatabaseManager:
    """Manages SQLAlchemy engine and session creation."""
    
    def __init__(self, database_url: str):
        """
        Initialize database manager with connection URL.
        
        Args:
            database_url: PostgreSQL connection string (e.g., postgresql://user:pass@host:port/db)
        """
        self.database_url = database_url
        
        self.engine = create_engine(
            database_url,
            pool_pre_ping=True,
            echo=False,
        )
        
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
    
    def init_db(self) -> None:
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables initialized successfully")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Context manager for database sessions.
        
        Yields:
            Session: SQLAlchemy session object
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


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
    async def get_session(self) -> AsyncIterator[AsyncSession]:
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
