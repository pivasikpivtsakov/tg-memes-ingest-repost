"""
Shared package containing common modules accessible to all apps.
"""
from .storage import MediaStorage, MediaMetadata
from .config import BaseConfig

__all__ = [
    'MediaStorage',
    'MediaMetadata',
    'BaseConfig',
]

