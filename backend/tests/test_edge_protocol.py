import zlib

import numpy as np
import pytest

from app.services.edge_protocol import (
    FRAME_HEADER,
    FrameTransform,
    bgr_to_rgb565_le,
    letterbox_rgb565,
    pack_frame,
    restore_bbox,
    unpack_frame,
)


def test_rgb565_uses_little_endian_wire_order():
    pixel = np.array([[[0, 0, 255]]], dtype=np.uint8)
    assert bgr_to_rgb565_le(pixel) == b"\x00\xf8"


def test_frame_packet_round_trip_and_crc_rejection():
    payload = bytes(range(16))
    packet = pack_frame(42, payload, 4, 2, capture_timestamp_us=123456)
    header, decoded = unpack_frame(packet)
    assert header.frame_id == 42
    assert header.capture_timestamp_us == 123456
    assert header.payload_crc32 == zlib.crc32(payload) & 0xFFFFFFFF
    assert decoded == payload

    corrupt = bytearray(packet)
    corrupt[FRAME_HEADER.size] ^= 0xFF
    with pytest.raises(ValueError, match="CRC"):
        unpack_frame(bytes(corrupt))


def test_bbox_is_restored_from_letterboxed_edge_coordinates():
    transform = FrameTransform(1280, 720, 288, 160, 0.2222222, 2, 0)
    restored = restore_bbox([2, 0, 286, 160], transform)
    assert restored[0] == pytest.approx(0)
    assert restored[1] == pytest.approx(0)
    assert restored[2] == pytest.approx(1278, abs=1)
    assert restored[3] == pytest.approx(720)


def test_square_bootstrap_model_is_preconditioned_without_stretching_people():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    payload, transform = letterbox_rgb565(
        frame,
        target_width=288,
        target_height=160,
        model_width=224,
        model_height=224,
    )

    assert len(payload) == 288 * 160 * 2
    assert transform.pad_x == 0
    assert transform.pad_y == 35
    assert transform.scale == pytest.approx(288 / 1280)
    assert transform.scale_y == pytest.approx(90 / 720)
    assert restore_bbox([0, 35, 288, 125], transform) == pytest.approx([0, 0, 1280, 720])
