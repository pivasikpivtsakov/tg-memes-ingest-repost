from fractions import Fraction
from io import BytesIO

import av
from av.video.codeccontext import VideoCodecContext

TELEGRAM_SERVER_THUMB_MAX_FILE_SIZE = 10 * 1000 * 1000
THUMB_MAX_SIDE = 320
THUMB_SEEK_SECONDS = 1.0


def needs_own_thumbnail(file_size: int) -> bool:
    return file_size >= TELEGRAM_SERVER_THUMB_MAX_FILE_SIZE


def _thumb_size(width: int, height: int) -> tuple[int, int]:
    scale = min(1.0, THUMB_MAX_SIDE / max(width, height))
    thumb_width = max(2, int(width * scale) // 2 * 2)
    thumb_height = max(2, int(height * scale) // 2 * 2)
    return thumb_width, thumb_height


def generate_video_thumbnail(video_data: bytes) -> bytes:
    with av.open(BytesIO(video_data)) as container:
        stream = container.streams.video[0]
        duration_seconds = float(container.duration / av.time_base) if container.duration else 0.0
        seek_seconds = min(THUMB_SEEK_SECONDS, duration_seconds / 2)
        if seek_seconds > 0 and stream.time_base:
            container.seek(int(seek_seconds / stream.time_base), stream=stream)
        frame = next(container.decode(stream))

    thumb_width, thumb_height = _thumb_size(width=frame.width, height=frame.height)
    thumb_frame = frame.reformat(width=thumb_width, height=thumb_height, format="yuvj420p")

    encoder: VideoCodecContext = av.CodecContext.create("mjpeg", "w")
    encoder.width = thumb_width
    encoder.height = thumb_height
    encoder.pix_fmt = "yuvj420p"
    encoder.time_base = Fraction(1, 1)
    packets = encoder.encode(thumb_frame) + encoder.encode(None)
    return bytes(packets[0])
