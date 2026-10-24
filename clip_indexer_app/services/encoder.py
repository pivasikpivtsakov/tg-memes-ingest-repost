import logging
from pathlib import Path

import numpy as np
import open_clip
import torch
import torch.nn.functional as F
from open_clip.model import _build_vision_tower
from PIL import Image
from safetensors.torch import load_file

from shared.search.clip import CLIP_MODEL_NAME, CLIP_PRETRAINED, ensure_tower_weights

logger = logging.getLogger(__name__)


def resolve_device(device: str) -> torch.device:
    if device == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(device)


class ClipImageEncoder:
    """Vision tower only: the text tower is 3x larger and not needed for indexing."""

    def __init__(self, *, models_dir: Path, device: str, batch_size: int) -> None:
        self._models_dir = models_dir
        self._device = resolve_device(device)
        self._batch_size = batch_size
        self._tower: torch.nn.Module | None = None
        self._preprocess = None

    @property
    def device(self) -> torch.device:
        return self._device

    def load(self) -> None:
        model_cfg = open_clip.get_model_config(CLIP_MODEL_NAME)
        tower = _build_vision_tower(model_cfg["embed_dim"], model_cfg["vision_cfg"])
        tower.load_state_dict(load_file(ensure_tower_weights(self._models_dir, "visual")))
        self._tower = tower.eval().to(self._device)

        preprocess_cfg = open_clip.get_pretrained_cfg(CLIP_MODEL_NAME, CLIP_PRETRAINED)
        self._preprocess = open_clip.image_transform(
            tower.image_size,
            is_train=False,
            mean=preprocess_cfg["mean"],
            std=preprocess_cfg["std"],
            resize_mode=preprocess_cfg["resize_mode"],
            interpolation=preprocess_cfg["interpolation"],
        )
        logger.info(f"CLIP vision tower loaded on {self._device}")

    def preprocess(self, image: Image.Image) -> torch.Tensor:
        return self._preprocess(image)

    @torch.inference_mode()
    def encode(self, pixels: list[torch.Tensor]) -> np.ndarray:
        """L2-normalized embeddings, one row per preprocessed frame."""
        chunks = []
        for start in range(0, len(pixels), self._batch_size):
            batch = torch.stack(pixels[start:start + self._batch_size]).to(self._device)
            chunks.append(F.normalize(self._tower(batch), dim=-1).float().cpu())
        return torch.cat(chunks).numpy()
