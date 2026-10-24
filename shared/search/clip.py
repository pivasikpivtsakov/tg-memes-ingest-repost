import logging
import os
import tempfile
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

CLIP_MODEL_NAME = "xlm-roberta-base-ViT-B-32"
CLIP_PRETRAINED = "laion5b_s13b_b90k"
CLIP_MODEL_TAG = f"{CLIP_MODEL_NAME}/{CLIP_PRETRAINED}"

ClipTower = Literal["visual", "text"]
_TOWERS: tuple[ClipTower, ...] = ("visual", "text")
_CHECKPOINT_FILENAME = "open_clip_pytorch_model.bin"


def tower_weights_path(models_dir: Path, tower: ClipTower) -> Path:
    return models_dir / "clip" / f"{CLIP_MODEL_NAME}_{CLIP_PRETRAINED}_{tower}.safetensors"


def ensure_tower_weights(models_dir: Path, tower: ClipTower) -> Path:
    """Path to the weights of one tower, extracting them on first use.

    The full checkpoint is 1.46 GB, mostly the XLM-R text tower; each process
    loads only the tower it needs.
    """
    path = tower_weights_path(models_dir, tower)
    if not path.exists():
        _extract_towers(models_dir)
    return path


def _extract_towers(models_dir: Path) -> None:
    import open_clip
    from huggingface_hub import hf_hub_download

    repo_id = open_clip.get_pretrained_cfg(CLIP_MODEL_NAME, CLIP_PRETRAINED)["hf_hub"].rstrip("/")
    target_dir = tower_weights_path(models_dir, "visual").parent
    target_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=target_dir) as download_dir:
        logger.info(f"Downloading CLIP checkpoint {repo_id} to extract tower weights")
        checkpoint_path = hf_hub_download(repo_id, _CHECKPOINT_FILENAME, local_dir=download_dir)
        extract_towers_from_checkpoint(Path(checkpoint_path), models_dir)


def extract_towers_from_checkpoint(checkpoint_path: Path, models_dir: Path) -> None:
    import torch
    from safetensors.torch import save_file

    checkpoint = torch.load(checkpoint_path, map_location="cpu", mmap=True, weights_only=True)
    state_dict = checkpoint.get("state_dict", checkpoint)
    for tower in _TOWERS:
        prefixes = (f"module.{tower}.", f"{tower}.")
        tensors = {
            key.removeprefix(prefixes[0]).removeprefix(prefixes[1]): tensor.contiguous()
            for key, tensor in state_dict.items()
            if key.startswith(prefixes)
        }
        if not tensors:
            raise ValueError(f"No {tower} weights in {checkpoint_path}")
        path = tower_weights_path(models_dir, tower)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial_path = path.with_name(f"{path.name}.{os.getpid()}.partial")
        save_file(tensors, partial_path)
        partial_path.rename(path)
        logger.info(f"Saved {len(tensors)} {tower} tensors to {path}")
