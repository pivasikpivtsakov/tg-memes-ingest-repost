from importlib.metadata import version
from pathlib import Path

from PIL import Image
from rapidocr import RapidOCR
from rapidocr.utils.typings import EngineType, LangDet, LangRec, ModelType, OCRVersion

from shared.device import onnx_cuda_available, require_cuda_provider, resolve_device, validate_device
from shared.search.text import normalize_text

OCR_ENGINE_TAG = f"rapidocr-{version('rapidocr')}/PP-OCRv5-mobile-det/eslav-PP-OCRv5-mobile-rec"


class MemeTextReader:
    """RapidOCR with the East Slavic + English recognizer and no orientation classifier."""

    def __init__(self, *, models_dir: Path, threads: int, device: str = "cpu") -> None:
        self._models_dir = models_dir / "rapidocr"
        self._threads = threads
        self._device_request = "cpu"
        self._resolved_device: str | None = None
        self.device = device
        self._engine: RapidOCR | None = None

    @property
    def device(self) -> str:
        if self._resolved_device is None:
            self._resolved_device = resolve_device(
                self._device_request,
                cuda_available=onnx_cuda_available,
                cuda_missing="Install onnxruntime-gpu[cuda,cudnn] in place of onnxruntime.",
            )
        return self._resolved_device

    @device.setter
    def device(self, device: str) -> None:
        self._device_request = validate_device(device)
        self._resolved_device = None

    def load(self) -> None:
        use_cuda = self.device == "cuda"
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
        self._engine(blank, use_det=True, use_cls=False, use_rec=False)
        self._engine(blank, use_det=False, use_cls=False, use_rec=True)
        if use_cuda:
            self._require_cuda()

    def _require_cuda(self) -> None:
        for name in ("text_det", "text_rec"):
            stage = getattr(self._engine, name)
            require_cuda_provider(stage.session.session.get_providers(), component=f"OCR {name}")

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
