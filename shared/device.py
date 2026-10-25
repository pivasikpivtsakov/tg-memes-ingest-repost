"""Choose cpu or cuda the same way in every app.

``auto`` follows the runtime that will actually run the model. A GPU visible to
PyTorch is not a GPU ONNX Runtime can execute on: the two stacks ship different
CUDA builds.
"""

import argparse
from collections.abc import Callable, Sequence
from typing import Literal

DeviceChoice = Literal["auto", "cpu", "cuda"]
DeviceName = Literal["cpu", "cuda"]

DEVICE_CHOICES: tuple[DeviceChoice, ...] = ("auto", "cpu", "cuda")


def validate_device(device: str, *, name: str = "device") -> DeviceChoice:
    if device not in DEVICE_CHOICES:
        raise ValueError(f"{name} must be 'auto', 'cpu' or 'cuda', got {device!r}")
    return device  # type: ignore[return-value]


def resolve_device(
    device: str,
    *,
    cuda_available: Callable[[], bool],
    cuda_missing: str = "",
) -> DeviceName:
    """``auto`` uses CUDA when ``cuda_available`` says so; explicit cuda requires it."""
    choice = validate_device(device)
    if choice == "cpu":
        return "cpu"
    if cuda_available():
        return "cuda"
    if choice == "auto":
        return "cpu"
    detail = f" {cuda_missing}" if cuda_missing else ""
    raise RuntimeError(f"CUDA was requested, but no GPU runtime is available.{detail}")


def torch_cuda_available() -> bool:
    import torch
    return torch.cuda.is_available()


def onnx_cuda_available() -> bool:
    """True when ONNX Runtime can execute on CUDA.

    Preload first: the CUDA 13 wheel does not see torch's CUDA 12 libraries.
    """
    import onnxruntime
    onnxruntime.preload_dlls(cuda=True, cudnn=True)
    return "CUDAExecutionProvider" in onnxruntime.get_available_providers()


def require_cuda_provider(providers: Sequence[str], *, component: str) -> None:
    """Fail when a session was asked for CUDA and the runtime fell back to CPU."""
    if "CUDAExecutionProvider" not in providers:
        raise RuntimeError(
            f"{component} is not using CUDA (providers: {list(providers)}). "
            "Install onnxruntime-gpu[cuda,cudnn] in place of onnxruntime."
        )


def add_device_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--device",
        choices=DEVICE_CHOICES,
        help="override the configured device: auto (GPU when this app can use it), cpu, or cuda",
    )
