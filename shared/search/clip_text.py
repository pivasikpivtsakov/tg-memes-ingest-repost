from pathlib import Path

import numpy as np
import open_clip
import torch
import torch.nn.functional as F
from open_clip.model import _build_text_tower
from safetensors.torch import load_file

from shared.search.clip import CLIP_MODEL_NAME, ensure_tower_weights


class ClipTextEncoder:
    """Text tower of the multilingual CLIP; runs on CPU next to the indexing daemons."""

    def __init__(self, *, models_dir: Path) -> None:
        self._models_dir = models_dir
        self._tower: torch.nn.Module | None = None
        self._tokenizer = None

    def load(self) -> None:
        model_cfg = open_clip.get_model_config(CLIP_MODEL_NAME)
        text_cfg = {**model_cfg["text_cfg"], "hf_model_pretrained": False}
        tower = _build_text_tower(model_cfg["embed_dim"], text_cfg)
        # The checkpoint carries a position_ids buffer that newer transformers no longer register.
        missing, _ = tower.load_state_dict(
            load_file(ensure_tower_weights(self._models_dir, "text")),
            strict=False,
        )
        if missing:
            raise RuntimeError(f"CLIP text weights are missing keys: {missing}")
        self._tower = tower.eval()
        self._tokenizer = open_clip.get_tokenizer(CLIP_MODEL_NAME)

    @torch.inference_mode()
    def encode(self, query: str) -> np.ndarray:
        if self._tower is None:
            self.load()
        features = self._tower(self._tokenizer([query]))
        return F.normalize(features, dim=-1)[0].numpy()
