from __future__ import annotations

import struct
import time
import zlib
from dataclasses import dataclass

import cv2
import numpy as np


FRAME_MAGIC = b"VEC1"
FRAME_VERSION = 1
PIXEL_FORMAT_RGB565_LE = 1
FRAME_HEADER = struct.Struct("<4sBBHIQHHI")


@dataclass(frozen=True)
class FrameHeader:
    frame_id: int
    capture_timestamp_us: int
    width: int
    height: int
    flags: int
    pixel_format: int
    payload_crc32: int


@dataclass(frozen=True)
class FrameTransform:
    source_width: int
    source_height: int
    target_width: int
    target_height: int
    scale: float
    pad_x: int
    pad_y: int
    scale_y: float | None = None


def bgr_to_rgb565_le(frame: np.ndarray) -> bytes:
    # Use native OpenCV SIMD vectorized conversion for sub-millisecond execution
    return cv2.cvtColor(frame, cv2.COLOR_BGR2BGR565).tobytes()


def letterbox_rgb565(
    frame: np.ndarray,
    target_width: int = 288,
    target_height: int = 160,
    *,
    model_width: int | None = None,
    model_height: int | None = None,
) -> tuple[bytes, FrameTransform]:
    source_height, source_width = frame.shape[:2]
    model_width = model_width or target_width
    model_height = model_height or target_height
    if min(source_width, source_height, target_width, target_height, model_width, model_height) <= 0:
        raise ValueError("frame and model dimensions must be positive")

    # ESP-DL's bootstrap model resizes the 288x160 wire image to 224x224.
    # Build the letterbox in model space and map it back to wire space so that
    # the device resize preserves human proportions instead of stretching them.
    model_scale = min(model_width / source_width, model_height / source_height)
    model_resized_width = max(1, round(source_width * model_scale))
    model_resized_height = max(1, round(source_height * model_scale))
    resized_width = max(1, round(model_resized_width * target_width / model_width))
    resized_height = max(1, round(model_resized_height * target_height / model_height))
    resized_width = min(target_width, resized_width)
    resized_height = min(target_height, resized_height)
    resized = cv2.resize(frame, (resized_width, resized_height), interpolation=cv2.INTER_AREA)
    canvas = np.full((target_height, target_width, 3), 114, dtype=np.uint8)
    pad_x = (target_width - resized_width) // 2
    pad_y = (target_height - resized_height) // 2
    canvas[pad_y:pad_y + resized_height, pad_x:pad_x + resized_width] = resized
    scale_x = resized_width / source_width
    scale_y = resized_height / source_height
    return bgr_to_rgb565_le(canvas), FrameTransform(
        source_width=source_width,
        source_height=source_height,
        target_width=target_width,
        target_height=target_height,
        scale=scale_x,
        pad_x=pad_x,
        pad_y=pad_y,
        scale_y=scale_y,
    )


def pack_frame(
    frame_id: int,
    payload: bytes,
    width: int,
    height: int,
    *,
    flags: int = 0,
    capture_timestamp_us: int | None = None,
) -> bytes:
    timestamp = capture_timestamp_us if capture_timestamp_us is not None else time.time_ns() // 1_000
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    header = FRAME_HEADER.pack(
        FRAME_MAGIC,
        FRAME_VERSION,
        PIXEL_FORMAT_RGB565_LE,
        flags,
        frame_id,
        timestamp,
        width,
        height,
        crc,
    )
    return header + payload


def unpack_frame(packet: bytes) -> tuple[FrameHeader, bytes]:
    if len(packet) < FRAME_HEADER.size:
        raise ValueError("frame packet is shorter than its header")
    magic, version, pixel_format, flags, frame_id, timestamp, width, height, crc = FRAME_HEADER.unpack_from(packet)
    if magic != FRAME_MAGIC or version != FRAME_VERSION:
        raise ValueError("unsupported edge frame protocol")
    payload = packet[FRAME_HEADER.size:]
    if len(payload) != width * height * 2:
        raise ValueError("RGB565 payload length does not match frame dimensions")
    if zlib.crc32(payload) & 0xFFFFFFFF != crc:
        raise ValueError("frame payload CRC mismatch")
    return FrameHeader(frame_id, timestamp, width, height, flags, pixel_format, crc), payload


def restore_bbox(bbox: list[float], transform: FrameTransform) -> list[float]:
    x1, y1, x2, y2 = bbox
    scale_y = transform.scale if transform.scale_y is None else transform.scale_y
    restored = [
        (x1 - transform.pad_x) / transform.scale,
        (y1 - transform.pad_y) / scale_y,
        (x2 - transform.pad_x) / transform.scale,
        (y2 - transform.pad_y) / scale_y,
    ]
    restored[0] = min(max(restored[0], 0.0), float(transform.source_width))
    restored[2] = min(max(restored[2], 0.0), float(transform.source_width))
    restored[1] = min(max(restored[1], 0.0), float(transform.source_height))
    restored[3] = min(max(restored[3], 0.0), float(transform.source_height))
    return restored
