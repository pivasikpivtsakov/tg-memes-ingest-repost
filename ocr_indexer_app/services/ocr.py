import logging
from importlib.metadata import version
from pathlib import Path

from PIL import Image
from rapidocr import RapidOCR
from rapidocr.utils.typings import EngineType, LangDet, LangRec, ModelType, OCRVersion

from shared.device import (
    DeviceChoice,
    DeviceName,
    onnx_cuda_available,
    require_cuda_provider,
    resolve_device,
)
from shared.search.text import normalize_text

logger = logging.getLogger(__name__)

OCR_ENGINE_TAG = f"rapidocr-{version('rapidocr')}/PP-OCRv5-mobile-det/eslav-PP-OCRv5-mobile-rec"


class MemeTextReader:
    """RapidOCR with the East Slavic + English recognizer and no orientation classifier."""

    def __init__(
        self,
        *,
        models_dir: Path,
        threads: int,
        device: DeviceChoice = DeviceChoice.CPU,
    ) -> None:
        self._models_dir = models_dir / "rapidocr"
        self._threads = threads
        self._device_request = device
        self._resolved_device: DeviceName | None = None
        self._engine: RapidOCR | None = None

    @property
    def device(self) -> DeviceName:
        if self._resolved_device is None:
            self._resolved_device = resolve_device(
                self._device_request,
                cuda_available=onnx_cuda_available,
                cuda_missing="Install onnxruntime-gpu[cuda,cudnn] in place of onnxruntime.",
            )
        return self._resolved_device

    @device.setter
    def device(self, device: DeviceChoice) -> None:
        self._device_request = device
        self._resolved_device = None

    def load(self) -> None:
        use_cuda = self.device == DeviceName.CUDA
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
            "EngineConfig.onnxruntime.use_cuda": use_cuda,
        })
        # RapidOCR loads (and on first run downloads) each model on its first use.
        blank = Image.new("RGB", (64, 64), "white")
        logger.info("Loading OCR detection model")
        self._engine(blank, use_det=True, use_cls=False, use_rec=False)
        logger.info("Loading OCR recognition model")
        self._engine(blank, use_det=False, use_cls=False, use_rec=True)
        logger.info(f"OCR models loaded on {self.device}")
        if use_cuda:
            self._require_cuda()

    def _require_cuda(self) -> None:
        for name in ("text_det", "text_rec"):
            stage = getattr(self._engine, name)
            require_cuda_provider(stage.session.session.get_providers(), component=f"OCR {name}")

    def read(self, frames: list[Image.Image]) -> str:
        """Recognized lines of all frames, without lines repeated across video frames."""
        engine = self._engine
        if engine is None:
            raise RuntimeError("OCR engine is not loaded")
        lines: list[str] = []
        seen: set[str] = set()
        for frame in frames:
            result = engine(frame, use_det=True, use_cls=False, use_rec=True)
            for line in result.txts or ():
                key = normalize_text(line)
                if key and key not in seen:
                    seen.add(key)
                    lines.append(line.strip())
        return "\n".join(lines)
