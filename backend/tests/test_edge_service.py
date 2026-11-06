import time

import pytest

from app.config import Settings
from app.services.edge_inference_service import EdgeInferenceService, PendingFrame
from app.services.edge_protocol import FrameTransform
from app.services.state import RuntimeState


class FakeWebSocket:
    def __init__(self):
        self.json_messages = []
        self.closed = None

    async def send_json(self, payload):
        self.json_messages.append(payload)

    async def send_bytes(self, _payload):
        pass

    async def close(self, code=1000, reason=""):
        self.closed = (code, reason)


@pytest.mark.asyncio
async def test_occupancy_includes_active_configuration_revision():
    state = RuntimeState()
    state.edge.configuration_revision = 7
    service = EdgeInferenceService(Settings(auto_start_camera=False), state)
    websocket = FakeWebSocket()
    await service.connect(websocket)

    await service.send_occupancy({1: 1, 2: 0})

    message = websocket.json_messages[-1]
    assert message["type"] == "occupancy"
    assert message["configuration_revision"] == 7
    assert message["zones"] == [
        {"zone_id": 1, "occupied": True, "people_count": 1},
        {"zone_id": 2, "occupied": False, "people_count": 0},
    ]


def test_late_edge_result_is_rejected_without_replacing_tracks():
    state = RuntimeState()
    service = EdgeInferenceService(Settings(auto_start_camera=False), state)
    transform = FrameTransform(1280, 720, 288, 160, 0.2222222, 2, 0)
    service._pending_frame = PendingFrame(9, time.monotonic(), transform)

    service._handle_inference_result({"type": "inference_result", "frame_id": 8, "detections": []})

    assert state.edge.late_results == 1
    assert service._pending_frame.frame_id == 9
    assert service.pop_latest_result() is None


@pytest.mark.asyncio
async def test_model_hash_mismatch_latches_safe_emergency_and_disconnects():
    state = RuntimeState()
    settings = Settings(auto_start_camera=False, edge_expected_model_sha256="expected")
    service = EdgeInferenceService(settings, state)
    websocket = FakeWebSocket()
    await service.connect(websocket)

    await service._handle_hello({
        "type": "hello",
        "protocol": 1,
        "input_width": 288,
        "input_height": 160,
        "model_sha256": "wrong",
    })

    assert websocket.json_messages[-1]["type"] == "emergency"
    assert websocket.json_messages[-1]["active"] is True
    assert websocket.closed[0] == 1008
    assert service.connected is False
    assert state.detection.model_loaded is False
