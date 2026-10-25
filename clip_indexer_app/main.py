import logging
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import torch

from clip_indexer_app.config import ClipIndexerConfig, config
from clip_indexer_app.services import ClipImageEncoder
from shared.db.repositories import ClipEmbeddingRepository, ClipEmbeddingRow
from shared.indexer_base import AbstractIndexerApp, DownloadedMedia, IndexBatchResult
from shared.search.clip import CLIP_MODEL_TAG
from shared.search.frames import load_frames

logger = logging.getLogger(__name__)

# The vision tower sees 224px crops; 640 keeps the short side above that even for tall memes.
_FRAME_MAX_SIDE = 640


class ClipIndexerApp(AbstractIndexerApp[ClipEmbeddingRow]):
    repository_cls = ClipEmbeddingRepository

    def __init__(self, config: ClipIndexerConfig):
        super().__init__(config)
        self.config = config
        self.encoder = ClipImageEncoder(
            models_dir=config.models_dir,
            device=config.clip_device,
            batch_size=config.clip_encode_batch_size,
        )
        self._decode_pool = ThreadPoolExecutor(max_workers=config.clip_decode_threads)

    def _apply_device(self, device: str) -> None:
        self.encoder.device = device

    def _load_model(self) -> None:
        self.encoder.load()

    def _preprocess(self, item: DownloadedMedia) -> list[torch.Tensor] | None:
        media = item.media
        try:
            frames = load_frames(
                item.data,
                media.media_type,
                video_frames=self.config.clip_video_frames,
                max_side=_FRAME_MAX_SIDE,
            )
            return [self.encoder.preprocess(frame) for frame in frames]
        except Exception as e:
            logger.warning(f"Failed to decode {media.media_type} #{media.id}: {e}")
            return None

    def _index_batch(self, items: list[DownloadedMedia]) -> IndexBatchResult[ClipEmbeddingRow]:
        pixels: list[torch.Tensor] = []
        spans: list[tuple[int, int, int]] = []
        failed_ids: list[int] = []
        for item, media_pixels in zip(items, self._decode_pool.map(self._preprocess, items)):
            if media_pixels is None:
                failed_ids.append(item.media.id)
                continue
            spans.append((item.media.id, len(pixels), len(media_pixels)))
            pixels.extend(media_pixels)

        if not pixels:
            return IndexBatchResult(rows=[], failed_ids=failed_ids)

        embeddings = self.encoder.encode(pixels)
        rows = []
        for media_id, start, count in spans:
            embedding = embeddings[start:start + count].mean(axis=0)
            rows.append(ClipEmbeddingRow(
                media_id=media_id,
                embedding=embedding / np.linalg.norm(embedding),
                model=CLIP_MODEL_TAG,
                frame_count=count,
            ))
        return IndexBatchResult(rows=rows, failed_ids=failed_ids)

    def _log_startup_info(self) -> None:
        logger.info("CLIP Indexer App Starting")
        logger.info(f"Model: {CLIP_MODEL_TAG}")
        logger.info(f"Device: {self.encoder.device}")
        logger.info(
            f"Batch: {self.config.batch_size} medias, "
            f"{self.config.clip_encode_batch_size} frames per forward pass"
        )
        logger.info(f"Frames per video: {self.config.clip_video_frames}")


def run() -> None:
    app = ClipIndexerApp(config)
    app.run()


if __name__ == '__main__':
    run()
