from importlib.metadata import version
from pathlib import Path

from PIL import Image
from rapidocr import RapidOCR
from rapidocr.utils.typings import EngineType, LangDet, LangRec, ModelType, OCRVersion

from shared.search.text import normalize_text

OCR_ENGINE_TAG = f"rapidocr-{version('rapidocr')}/PP-OCRv5-mobile-det/eslav-PP-OCRv5-mobile-rec"


class MemeTextReader:
    """RapidOCR on CPU with the East Slavic + English recognizer and no orientation classifier."""

    def __init__(self, *, models_dir: Path, threads: int) -> None:
        self._models_dir = models_dir / "rapidocr"
        self._threads = threads
        self._engine: RapidOCR | None = None

    def load(self) -> None:
        self._models_dir.mkdir(parents=True, exist_ok=True)
        self._engine = RapidOCR(params={
            "Global.use_cls": False,
            "Global.log_level": "error",
            "Global.model_root_dir": str(self._models_dir),
            "Det.engine_type": EngineType.ONNXRUNTIME,
            "Det.lang_type": LangDet.MULTI,
            "Det.model_type": ModelType.MOBILE,
            "Det.ocr_version": OCRVersion.PPOCRV5,
            "Rec.engine_type": EngineType.ONNXRUNTIME,
            "Rec.lang_type": LangRec.ESLAV,
            "Rec.model_type": ModelType.MOBILE,
            "Rec.ocr_version": OCRVersion.PPOCRV5,
            "EngineConfig.onnxruntime.intra_op_num_threads": self._threads,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        })
        # RapidOCR loads (and on first run downloads) each model on its first use.
        blank = Image.new("RGB", (64, 64), "white")
        self._engine(blank, use_det=True, use_cls=False, use_rec=False)
        self._engine(blank, use_det=False, use_cls=False, use_rec=True)

    def read(self, frames: list[Image.Image]) -> str:
        """Recognized lines of all frames, without lines repeated across video frames."""
        lines: list[str] = []
        seen: set[str] = set()
        for frame in frames:
            result = self._engine(frame, use_det=True, use_cls=False, use_rec=True)
            for line in result.txts or ():
                key = normalize_text(line)
                if key and key not in seen:
                    seen.add(key)
                    lines.append(line.strip())
        return "\n".join(lines)
