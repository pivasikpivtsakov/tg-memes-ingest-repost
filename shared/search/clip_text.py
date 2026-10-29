import logging
from pathlib import Path

import numpy as np
import open_clip
import torch
import torch.nn.functional as F
from open_clip.model import _build_text_tower
from safetensors.torch import load_file

from shared.device import DeviceChoice, resolve_device, torch_cuda_available
from shared.search.clip import CLIP_MODEL_NAME, ClipTower, ensure_tower_weights

logger = logging.getLogger(__name__)


class ClipTextEncoder:
    """Text tower of the multilingual CLIP."""

    def __init__(self, *, models_dir: Path, device: DeviceChoice) -> None:
        self._models_dir = models_dir
        self._device_request = device
        self._device: torch.device | None = None
        self._tower: torch.nn.Module | None = None
        self._tokenizer = None

    def load(self) -> None:
        device = torch.device(resolve_device(
            self._device_request,
            cuda_available=torch_cuda_available,
        ))
        logger.info(f"Building CLIP text tower for {device}")
        model_cfg = open_clip.get_model_config(CLIP_MODEL_NAME)
        text_cfg = {**model_cfg["text_cfg"], "hf_model_pretrained": False}
        tower = _build_text_tower(model_cfg["embed_dim"], text_cfg)
        weights = ensure_tower_weights(self._models_dir, ClipTower.TEXT)
        logger.info(f"Loading CLIP text weights from {weights}")
        # The checkpoint carries a position_ids buffer that newer transformers no longer register.
        missing, _ = tower.load_state_dict(load_file(weights), strict=False)
        if missing:
            raise RuntimeError(f"CLIP text weights are missing keys: {missing}")
        logger.info(f"Moving CLIP text tower to {device}")
        self._tower = tower.eval().to(device)
        logger.info("Loading CLIP tokenizer")
        self._tokenizer = open_clip.get_tokenizer(CLIP_MODEL_NAME)
        self._device = device
        # The first call sets padding on the Rust tokenizer; concurrent first calls would race on it.
        logger.info("Warming up CLIP text tower")
        self.encode("")
        logger.info(f"CLIP text tower loaded on {device}")

    @torch.inference_mode()
    def encode(self, query: str) -> np.ndarray:
        tower = self._tower
        tokenizer = self._tokenizer
        device = self._device
        if tower is None or tokenizer is None or device is None:
            raise RuntimeError("CLIP text tower is not loaded")
        features = tower(tokenizer([query]).to(device))
        return F.normalize(features, dim=-1)[0].float().cpu().numpy()
