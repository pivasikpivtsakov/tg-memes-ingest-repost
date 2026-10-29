from shared.device import DeviceChoice, validate_device
from shared.indexer_base import BaseIndexerConfig


class ClipIndexerConfig(BaseIndexerConfig):
    key_prefix = 'clip_indexer'
    default_batch_size = 32

    def __init__(self):
        super().__init__()

        # CLIP-specific settings
        self._clip_device = self._config_data.get('clip_device', 'auto')
        self._clip_video_frames = self._config_data.get('clip_video_frames', 8)
        self._clip_encode_batch_size = self._config_data.get('clip_encode_batch_size', 64)
        self._clip_decode_threads = self._config_data.get('clip_decode_threads', 2)

    @property
    def clip_device(self) -> DeviceChoice:
        """'auto' (CUDA when PyTorch can see a GPU), 'cuda' or 'cpu'."""
        return validate_device(str(self._clip_device), name='clip_device')

    @property
    def clip_video_frames(self) -> int:
        """Frames sampled per video; their embeddings are averaged."""
        return int(self._clip_video_frames)

    @property
    def clip_encode_batch_size(self) -> int:
        """Frames per forward pass of the vision tower."""
        return int(self._clip_encode_batch_size)

    @property
    def clip_decode_threads(self) -> int:
        """Threads decoding and resizing files before they reach the model."""
        return int(self._clip_decode_threads)


config = ClipIndexerConfig()
