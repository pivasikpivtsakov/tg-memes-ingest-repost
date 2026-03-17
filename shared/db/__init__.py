"""
Database module for ingestion_app.

Provides SQLAlchemy ORM models, session management, and database initialization.
"""
from shared.db.base import Base
from shared.db.models import Media
from shared.db.session import DatabaseManager

__all__ = ['Base', 'Media', 'DatabaseManager']
