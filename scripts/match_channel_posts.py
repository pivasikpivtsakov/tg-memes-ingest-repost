#!/usr/bin/env python3
"""Find the meme behind every post of the target channel and store the post id as its posted_message_id."""
import argparse
import asyncio
import logging
import math
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import av
import numpy as np
from botocore.exceptions import ClientError
from PIL import Image, ImageFilter
from telethon import TelegramClient
from telethon.tl.types import Message, MessageMediaPhoto

from clip_indexer_app.config import config as clip_config
from clip_indexer_app.services import ClipImageEncoder
from sender_tg_app.config import config
from shared.db.models import MediaType
from shared.db.repositories import ClipEmbeddingRepository, MediaRepository
from shared.db.repositories.media import MediaMetadata
from shared.db.session import AsyncDatabaseManager
from shared.logger import setup_logging
from shared.s3.client import create_s3_client
from shared.s3.repositories import ObjectRepository
from shared.search.clip import CLIP_FRAME_MAX_SIDE
from shared.search.frames import load_frames

logger = logging.getLogger(__name__)

_CHUNK = 200
_WORKERS = 8
# HNSW misses exact copies inside clusters of duplicates, so the search is exhaustive in memory.
# Posts scored >= 0.948 against the meme the sender recorded for them.
_CLIP_MIN_SIMILARITY = 0.93
# Plain text memes have hundreds of neighbours above the threshold.
_CLIP_MAX_CANDIDATES = 50
# Largest blurred difference: recompressed copies <= 45, screenshots differing in a few UI pixels >= 52.
_PIXEL_MAX_DIFF = 48
_HEAD_BYTES = 64 * 1024
# Ingestion never stores larger videos.
_MAX_VIDEO_BYTES = 50 * 1024 * 1024
_DECODE_ERRORS = (OSError, ValueError, IndexError, av.FFmpegError, Image.DecompressionBombError)


def _media_type(message: Message) -> MediaType | None:
    if message.fwd_from is not None:
        return None
    if isinstance(message.media, MessageMediaPhoto):
        return MediaType.PHOTO
    if message.document is not None and (message.document.mime_type or "").startswith("video/"):
        return MediaType.VIDEO
    return None


def _decode(data: bytes, media_type: MediaType) -> list[Image.Image]:
    return load_frames(data, media_type, video_frames=clip_config.clip_video_frames, max_side=CLIP_FRAME_MAX_SIDE)


def _gray(image: Image.Image, size: tuple[int, int]) -> np.ndarray:
    resized = image.convert("L").resize(size, Image.Resampling.LANCZOS)
    return np.asarray(resized.filter(ImageFilter.GaussianBlur(1)), dtype=np.float32)


def _same_image(a: Image.Image, b: Image.Image) -> bool:
    if abs(math.log(a.width * b.height / (a.height * b.width))) > 0.02:
        return False
    scale = 512 / max(a.size)
    size = (max(1, round(a.width * scale)), max(1, round(a.height * scale)))
    return float(np.abs(_gray(a, size) - _gray(b, size)).max()) <= _PIXEL_MAX_DIFF


async def _load_index(embeddings: ClipEmbeddingRepository, media_type: MediaType) -> tuple[np.ndarray, np.ndarray]:
    ids: list[int] = []
    vectors: list[np.ndarray] = []
    async for rows in embeddings.iter_by_media_type(media_type, batch_size=5000):
        ids += [row.media_id for row in rows]
        vectors.append(np.array([row.embedding for row in rows], dtype=np.float32))
    logger.info(f"{len(ids)} {media_type} embeddings loaded")
    return np.array(ids), np.concatenate(vectors)


@dataclass
class _Matcher:
    client: TelegramClient
    medias: MediaRepository
    objects: ObjectRepository
    encoder: ClipImageEncoder
    indexes: Mapping[MediaType, tuple[np.ndarray, np.ndarray]]
    videos_by_size: Mapping[int, Sequence[MediaMetadata]]
    gpu: asyncio.Lock = field(default_factory=asyncio.Lock)
    workers: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(_WORKERS))

    async def match(self, message: Message, media_type: MediaType) -> tuple[str, int | None]:
        async with self.workers:
            try:
                result = await self._match(message, media_type)
            except Exception as e:
                logger.warning(f"Post {message.id} failed: {e!r}")
                return "failed", None
        return result

    async def _match(self, message: Message, media_type: MediaType) -> tuple[str, int | None]:
        if media_type == MediaType.PHOTO:
            # 800px is enough for CLIP and the pixel check, and much lighter than the original.
            data = await self.client.download_media(message, file=bytes, thumb="x")
            if data is None:
                data = await self.client.download_media(message, file=bytes)
            media_id = await self._match_clip(data, media_type)
            return "photo", media_id

        # Telegram keeps videos byte for byte, but the size alone collides between videos.
        candidates = self.videos_by_size.get(message.document.size, ())
        if candidates:
            chunks = [c async for c in self.client.iter_download(message.document, request_size=_HEAD_BYTES, limit=1)]
            for media in candidates:
                theirs = await asyncio.to_thread(self._fetch, media.file_path, _HEAD_BYTES)
                if theirs == chunks[0]:
                    return "video bytes", media.id
        if message.document.size > _MAX_VIDEO_BYTES:
            return "video clip", None
        data = await self.client.download_media(message, file=bytes)
        media_id = await self._match_clip(data, media_type)
        return "video clip", media_id

    async def _match_clip(self, data: bytes, media_type: MediaType) -> int | None:
        frames = await asyncio.to_thread(_decode, data, media_type)
        async with self.gpu:
            candidate_ids = await asyncio.to_thread(self._nearest, frames, media_type)
        candidates = await self.medias.list_by_ids(candidate_ids)
        for media_id in sorted(candidates):
            theirs = await asyncio.to_thread(self._candidate_frames, candidates[media_id])
            if theirs is not None and len(theirs) == len(frames) and all(map(_same_image, frames, theirs, strict=True)):
                return media_id
        return None

    def _nearest(self, frames: Sequence[Image.Image], media_type: MediaType) -> list[int]:
        embedding = self.encoder.encode([self.encoder.preprocess(frame) for frame in frames]).mean(axis=0)
        ids, matrix = self.indexes[media_type]
        similarity = matrix @ (embedding / np.linalg.norm(embedding))
        above = np.flatnonzero(similarity >= _CLIP_MIN_SIMILARITY)
        return ids[above[np.argsort(-similarity[above])[:_CLIP_MAX_CANDIDATES]]].tolist()

    def _candidate_frames(self, media: MediaMetadata) -> list[Image.Image] | None:
        data = self._fetch(media.file_path, None)
        try:
            return None if data is None else _decode(data, media.media_type)
        except _DECODE_ERRORS as e:
            logger.warning(f"Meme {media.id} cannot be decoded, skipped as a candidate: {e!r}")
            return None

    def _fetch(self, key: str, size: int | None) -> bytes | None:
        try:
            return self.objects.get(key) if size is None else self.objects.get_head(key, size=size)
        except ClientError as e:
            if self.objects.is_missing(e):
                return None
            raise


async def _process(
    *,
    chunk: Sequence[tuple[Message, MediaType]],
    matcher: _Matcher,
    assigned: set[int],
    counts: Counter[str],
) -> None:
    results = await asyncio.gather(*(matcher.match(message, media_type) for message, media_type in chunk))
    writes: dict[int, int] = {}
    # Chunks go in channel order, so the earliest post of a meme takes it and later duplicates do not.
    for (message, _), (method, media_id) in zip(chunk, results, strict=True):
        if media_id is None:
            counts["failed" if method == "failed" else "no match"] += 1
        elif media_id in assigned:
            counts["taken by an earlier post"] += 1
        else:
            assigned.add(media_id)
            writes[media_id] = message.id
            counts[method] += 1
    await matcher.medias.set_posted_message_ids(writes)


async def main(*, chat_id: int, min_id: int) -> int:
    db = AsyncDatabaseManager(config.database_url)
    medias = MediaRepository(db)
    try:
        posted = await medias.list_by_where("posted_message_id IS NOT NULL")
        assigned = {media.id for media in posted}
        known_posts = {media.posted_message_id for media in posted}
        videos = await medias.list_by_where(f"media_type = '{MediaType.VIDEO}'")
        videos_by_size: dict[int, list[MediaMetadata]] = defaultdict(list)
        for video in videos:
            videos_by_size[video.file_size].append(video)
        indexes = {}
        for media_type in MediaType:
            indexes[media_type] = await _load_index(ClipEmbeddingRepository(db), media_type)
        encoder = ClipImageEncoder(
            models_dir=clip_config.models_dir,
            device=clip_config.clip_device,
            batch_size=clip_config.clip_encode_batch_size,
        )
        await asyncio.to_thread(encoder.load)
        s3 = create_s3_client(
            endpoint=config.minio_endpoint,
            access_key=config.minio_access_key,
            secret_key=config.minio_secret_key,
            secure=config.minio_secure,
        )
        client = TelegramClient(config.session_name, config.api_id, config.api_hash)
        client.flood_sleep_threshold = 24 * 3600
        matcher = _Matcher(
            client=client,
            medias=medias,
            objects=ObjectRepository(client=s3, bucket=config.minio_bucket),
            encoder=encoder,
            indexes=indexes,
            videos_by_size=videos_by_size,
        )
        counts: Counter[str] = Counter()
        chunk: list[tuple[Message, MediaType]] = []
        async with client:
            entity = await client.get_entity(chat_id)
            latest = await client.get_messages(entity, limit=1)
            started = time.monotonic()
            async for message in client.iter_messages(entity, reverse=True, min_id=min_id):
                media_type = _media_type(message)
                if media_type is None or message.id in known_posts:
                    continue
                chunk.append((message, media_type))
                if len(chunk) < _CHUNK:
                    continue
                await _process(chunk=chunk, matcher=matcher, assigned=assigned, counts=counts)
                chunk = []
                done = (message.id - min_id) / max(latest[0].id - min_id, 1)
                elapsed = time.monotonic() - started
                logger.info(f"{done:.1%} of the channel, {elapsed / done * (1 - done) / 60:.0f} min left | {dict(counts)}")
            await _process(chunk=chunk, matcher=matcher, assigned=assigned, counts=counts)
        logger.info(f"Done in {(time.monotonic() - started) / 60:.0f} min | {dict(counts)}")
        return 0
    finally:
        await db.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chat", type=int, default=int(config.target_chat_id))
    parser.add_argument("--min-id", type=int, default=0, help="start after this channel message id")
    args = parser.parse_args()
    setup_logging(logging.INFO)
    sys.exit(asyncio.run(main(chat_id=args.chat, min_id=args.min_id)))
