from io import BytesIO

import av
from av.container import InputContainer
from av.video.frame import VideoFrame
from av.video.stream import VideoStream
from PIL import Image, ImageOps

from shared.db.models import MediaType

# Past this, seeking to keyframes beats decoding the whole video for a few frames.
_SEEK_MIN_DURATION_SECONDS = 60.0


def load_frames(
    data: bytes,
    media_type: MediaType,
    *,
    video_frames: int,
    max_side: int,
) -> list[Image.Image]:
    """RGB frames of a media: the photo itself, or frames evenly spread over a video."""
    if media_type == MediaType.PHOTO:
        return [_load_photo(data, max_side=max_side)]
    return _sample_video(data, count=video_frames, max_side=max_side)


def _load_photo(data: bytes, *, max_side: int) -> Image.Image:
    with Image.open(BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    image.thumbnail((max_side, max_side))
    return image


def _sample_video(data: bytes, *, count: int, max_side: int) -> list[Image.Image]:
    with av.open(BytesIO(data)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        duration = _duration_seconds(container, stream)
        targets = [duration * (i + 0.5) / count for i in range(count)] if duration else [0.0]
        if duration and duration > _SEEK_MIN_DURATION_SECONDS:
            images = _decode_at_keyframes(container, stream, targets, max_side=max_side)
        else:
            images = _decode_sequentially(container, stream, targets, max_side=max_side)
    if not images:
        raise ValueError("video has no decodable frames")
    return images


def _decode_sequentially(
    container: InputContainer,
    stream: VideoStream,
    targets: list[float],
    *,
    max_side: int,
) -> list[Image.Image]:
    images: list[Image.Image] = []
    last_frame: VideoFrame | None = None
    next_target = 0
    # Frame timestamps count from the stream's start_time, targets from zero.
    start = float(stream.start_time * stream.time_base) if stream.start_time else 0.0
    for frame in container.decode(stream):
        last_frame = frame
        time = frame.time - start if frame.time is not None else 0.0
        if time < targets[next_target]:
            continue
        images.append(_frame_to_image(frame, max_side=max_side))
        while next_target < len(targets) and targets[next_target] <= time:
            next_target += 1
        if next_target == len(targets):
            break
    if not images and last_frame is not None:
        images.append(_frame_to_image(last_frame, max_side=max_side))
    return images


def _decode_at_keyframes(
    container: InputContainer,
    stream: VideoStream,
    targets: list[float],
    *,
    max_side: int,
) -> list[Image.Image]:
    images: list[Image.Image] = []
    start = stream.start_time or 0
    for target in targets:
        container.seek(start + int(target / stream.time_base), stream=stream)
        frame = next(container.decode(stream), None)
        if frame is not None:
            images.append(_frame_to_image(frame, max_side=max_side))
    return images


def _duration_seconds(container: InputContainer, stream: VideoStream) -> float | None:
    if container.duration:
        return container.duration / av.time_base
    if stream.duration and stream.time_base:
        return float(stream.duration * stream.time_base)
    return None


def _frame_to_image(frame: VideoFrame, *, max_side: int) -> Image.Image:
    scale = min(1.0, max_side / max(frame.width, frame.height))
    image = frame.to_image(
        width=max(1, round(frame.width * scale)),
        height=max(1, round(frame.height * scale)),
    )
    if frame.rotation:
        image = image.rotate(frame.rotation, expand=True)
    return image
