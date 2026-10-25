from importlib.metadata import version
from pathlib import Path

from PIL import Image
from rapidocr import RapidOCR
from rapidocr.utils.typings import EngineType, LangDet, LangRec, ModelType, OCRVersion

from shared.search.text import normalize_text

OCR_ENGINE_TAG = f"rapidocr-{version('rapidocr')}/PP-OCRv5-mobile-det/eslav-PP-OCRv5-mobile-rec"


class MemeTextReader:
    """RapidOCR with the East Slavic + English recognizer and no orientation classifier."""

    def __init__(self, *, models_dir: Path, threads: int, device: str = "cpu") -> None:
        self._models_dir = models_dir / "rapidocr"
        self._threads = threads
        self.device = device
        self._engine: RapidOCR | None = None

    def load(self) -> None:
        if self.device == "cuda":
            # The GPU wheel is CUDA 13 and does not see torch's CUDA 12 libraries.
            import onnxruntime
            onnxruntime.preload_dlls(cuda=True, cudnn=True)

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
            "EngineConfig.onnxruntime.use_cuda": self.device == "cuda",
        })
        # RapidOCR loads (and on first run downloads) each model on its first use.
        blank = Image.new("RGB", (64, 64), "white")
        self._engine(blank, use_det=True, use_cls=False, use_rec=False)
        self._engine(blank, use_det=False, use_cls=False, use_rec=True)
        if self.device == "cuda":
            self._require_cuda()

    def _require_cuda(self) -> None:
        for name in ("text_det", "text_rec"):
            stage = getattr(self._engine, name)
            providers = stage.session.session.get_providers()
            if "CUDAExecutionProvider" not in providers:
                raise RuntimeError(
                    f"OCR {name} is not using CUDA (providers: {providers}). "
                    "Install onnxruntime-gpu[cuda,cudnn] in place of onnxruntime."
                )

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
