import logging

from ocr_indexer_app.config import OcrIndexerConfig, config
from ocr_indexer_app.services import OCR_ENGINE_TAG, MemeTextReader
from shared.db.repositories import OcrRepository, OcrRow
from shared.indexer_base import AbstractIndexerApp, DownloadedMedia, IndexBatchResult
from shared.search.frames import load_frames
from shared.search.text import normalize_text

logger = logging.getLogger(__name__)

# Caps detector cost on large photos; meme text stays legible at this size.
_FRAME_MAX_SIDE = 1280


class OcrIndexerApp(AbstractIndexerApp[OcrRow, OcrIndexerConfig]):
    repository_cls = OcrRepository

    def __init__(self, config: OcrIndexerConfig):
        super().__init__(config)
        self.config = config
        self.reader = MemeTextReader(
            models_dir=config.models_dir,
            threads=config.ocr_threads,
            device=config.ocr_device,
        )

    def _apply_device(self, device: str) -> None:
        self.reader.device = device

    def _load_model(self) -> None:
        self.reader.load()

    def _index_batch(self, items: list[DownloadedMedia]) -> IndexBatchResult[OcrRow]:
        rows: list[OcrRow] = []
        failed_ids: list[int] = []
        for item in items:
            media = item.media
            try:
                frames = load_frames(
                    item.data,
                    media.media_type,
                    video_frames=self.config.ocr_video_frames,
                    max_side=_FRAME_MAX_SIDE,
                )
                text = self.reader.read(frames)
            except Exception as e:
                logger.warning(f"Failed to read text from {media.media_type} #{media.id}: {e}")
                failed_ids.append(media.id)
                continue
            rows.append(OcrRow(
                media_id=media.id,
                text=text,
                text_norm=normalize_text(text),
                engine=OCR_ENGINE_TAG,
            ))
        return IndexBatchResult(rows=rows, failed_ids=failed_ids)

    def _log_startup_info(self) -> None:
        logger.info("OCR Indexer App Starting")
        logger.info(f"Engine: {OCR_ENGINE_TAG}")
        logger.info(f"Device: {self.reader.device}")
        logger.info(f"Batch: {self.config.batch_size} medias, {self.config.ocr_threads} threads")
        logger.info(f"Frames per video: {self.config.ocr_video_frames}")


def run() -> None:
    app = OcrIndexerApp(config)
    app.run()


if __name__ == '__main__':
    run()
