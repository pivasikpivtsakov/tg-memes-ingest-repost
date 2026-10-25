import logging
from pathlib import Path

import numpy as np
import open_clip
import torch
import torch.nn.functional as F
from open_clip.model import _build_vision_tower
from PIL import Image
from safetensors.torch import load_file

from shared.device import resolve_device, torch_cuda_available, validate_device
from shared.search.clip import CLIP_MODEL_NAME, CLIP_PRETRAINED, ensure_tower_weights

logger = logging.getLogger(__name__)


class ClipImageEncoder:
    """Vision tower only: the text tower is 3x larger and not needed for indexing."""

    def __init__(self, *, models_dir: Path, device: str, batch_size: int) -> None:
        self._models_dir = models_dir
        self._batch_size = batch_size
        self._device_request = "cpu"
        self._device: torch.device | None = None
        self.device = device
        self._tower: torch.nn.Module | None = None
        self._preprocess = None

    @property
    def device(self) -> torch.device:
        if self._device is None:
            self._device = torch.device(resolve_device(
                self._device_request,
                cuda_available=torch_cuda_available,
            ))
        return self._device

    @device.setter
    def device(self, device: str) -> None:
        self._device_request = validate_device(device)
        self._device = None

    def load(self) -> None:
        model_cfg = open_clip.get_model_config(CLIP_MODEL_NAME)
        tower = _build_vision_tower(model_cfg["embed_dim"], model_cfg["vision_cfg"])
        tower.load_state_dict(load_file(ensure_tower_weights(self._models_dir, "visual")))
        self._tower = tower.eval().to(self.device)

        preprocess_cfg = open_clip.get_pretrained_cfg(CLIP_MODEL_NAME, CLIP_PRETRAINED)
        self._preprocess = open_clip.image_transform(
            tower.image_size,
            is_train=False,
            mean=preprocess_cfg["mean"],
            std=preprocess_cfg["std"],
            resize_mode=preprocess_cfg["resize_mode"],
            interpolation=preprocess_cfg["interpolation"],
        )
        logger.info(f"CLIP vision tower loaded on {self.device}")

    def preprocess(self, image: Image.Image) -> torch.Tensor:
        return self._preprocess(image)

    @torch.inference_mode()
    def encode(self, pixels: list[torch.Tensor]) -> np.ndarray:
        """L2-normalized embeddings, one row per preprocessed frame."""
        chunks = []
        for start in range(0, len(pixels), self._batch_size):
            batch = torch.stack(pixels[start:start + self._batch_size]).to(self.device)
            chunks.append(F.normalize(self._tower(batch), dim=-1).float().cpu())
        return torch.cat(chunks).numpy()
