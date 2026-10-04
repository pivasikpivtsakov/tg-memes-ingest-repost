"""
SQLAlchemy session management and database initialization.
"""
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from shared.db.base import Base

logger = logging.getLogger(__name__)


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
