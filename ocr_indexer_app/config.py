from shared.device import validate_device
from shared.indexer_base import BaseIndexerConfig


class OcrIndexerConfig(BaseIndexerConfig):
    key_prefix = 'ocr_indexer'
    default_batch_size = 16

    def __init__(self):
        super().__init__()

        # OCR-specific settings
        self._ocr_device = self._config_data.get('ocr_device', 'cpu')
        self._ocr_threads = self._config_data.get('ocr_threads', 3)
        self._ocr_video_frames = self._config_data.get('ocr_video_frames', 4)

    @property
    def ocr_device(self) -> str:
        """'cpu' (default; the 1060 stays free), 'cuda', or 'auto' when ONNX Runtime has CUDA."""
        return validate_device(str(self._ocr_device), name='ocr_device')

    @property
    def ocr_threads(self) -> int:
        """CPU threads for OCR inference; leaves the rest to Postgres and ingestion."""
        return int(self._ocr_threads)

    @property
    def ocr_video_frames(self) -> int:
        """Frames read per video; repeated lines are kept once."""
        return int(self._ocr_video_frames)


config = OcrIndexerConfig()
