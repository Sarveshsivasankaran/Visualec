from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from fastapi import WebSocket

from ..config import Settings
from .edge_protocol import FrameTransform, letterbox_rgb565, pack_frame, restore_bbox
from .state import RuntimeState


@dataclass
class PendingFrame:
    frame_id: int
    sent_at: float
    transform: FrameTransform
    send_done_at: float = 0.0


class EdgeInferenceService:
    """Owns the single, authenticated ESP32 edge session and latest-frame inference queue."""

    def __init__(self, settings: Settings, state: RuntimeState) -> None:
        self.settings = settings
        self.state = state
        self.websocket: WebSocket | None = None
        self._send_lock = asyncio.Lock()
        self._frame_sequence = 0
        self._pending_frame: PendingFrame | None = None
        self._latest_result: list[dict[str, Any]] | None = None
        self._last_send_at = 0.0
        self._previous_motion_gray: np.ndarray | None = None
        self._pending_commands: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._last_occupancy: dict[int, bool] = {}
        self._last_occupancy_send = 0.0

    @property
    def connected(self) -> bool:
        return self.websocket is not None

    async def connect(self, websocket: WebSocket) -> None:
        if self.websocket is not None:
            await self.websocket.close(code=1012, reason="superseded by a new edge connection")
        self.websocket = websocket
        self.state.esp32_connected = True
        self.state.edge.connected = True
        self.state.edge.last_seen_at = time.time()
        self.state.record_event("edge", "ESP32-S3 edge channel connected", source="ESP-DL", status="online")

    async def disconnect(self, websocket: WebSocket | None = None) -> None:
        if websocket is not None and websocket is not self.websocket:
            return
        self.websocket = None
        self._pending_frame = None
        self.state.esp32_connected = False
        self.state.edge.connected = False
        self.state.edge.inference_fps = 0.0
        self.state.detection.model_loaded = False
        self.state.detection.error = "ESP32-S3 edge inference offline"
        for future in self._pending_commands.values():
            if not future.done():
                future.set_exception(ConnectionError("edge device disconnected"))
        self._pending_commands.clear()
        self.state.record_event("edge", "ESP32-S3 edge channel disconnected", source="ESP-DL", status="offline")

    async def send_json(self, payload: dict[str, Any]) -> None:
        websocket = self.websocket
        if websocket is None:
            raise ConnectionError("edge device is not connected")
        async with self._send_lock:
            await websocket.send_json(payload)

    async def send_binary(self, payload: bytes) -> None:
        websocket = self.websocket
        if websocket is None:
            raise ConnectionError("edge device is not connected")
        async with self._send_lock:
            await websocket.send_bytes(payload)

    def motion_score(self, frame: np.ndarray) -> float:
        gray = cv2.cvtColor(cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        score = 1.0
        if self._previous_motion_gray is not None:
            delta = cv2.absdiff(gray, self._previous_motion_gray)
            score = float(np.count_nonzero(delta >= self.settings.edge_motion_pixel_threshold) / delta.size)
        self._previous_motion_gray = gray
        self.state.edge.motion_score = round(score, 4)
        return score

    def _cadence_seconds(self, motion_score: float, force: bool) -> float:
        if force or motion_score >= self.settings.edge_motion_high_threshold:
            return 1.0 / self.settings.edge_high_motion_fps
        if motion_score >= self.settings.edge_motion_medium_threshold:
            return 1.0 / self.settings.edge_medium_motion_fps
        return 1.0 / self.settings.edge_low_motion_fps

    async def maybe_send_frame(self, frame: np.ndarray, motion_score: float, *, force: bool = False) -> bool:
        if not self.connected:
            self.state.detection.error = "Waiting for ESP32-S3 edge inference"
            return False
        now = time.monotonic()
        if self._pending_frame is not None:
            if now - self._pending_frame.sent_at <= self.settings.edge_inference_timeout_seconds:
                self.state.edge.dropped_keyframes += 1
                return False
            self.state.edge.timed_out_frames += 1
            self._pending_frame = None
        cadence = self._cadence_seconds(motion_score, force)
        if now - self._last_send_at < cadence and now - self._last_send_at < self.settings.edge_mandatory_refresh_seconds:
            return False
        payload, transform = letterbox_rgb565(
            frame,
            target_width=self.settings.edge_input_width,
            target_height=self.settings.edge_input_height,
            model_width=self.state.edge.model_input_width,
            model_height=self.state.edge.model_input_height,
        )
        self._frame_sequence += 1
        packet = pack_frame(
            self._frame_sequence,
            payload,
            transform.target_width,
            transform.target_height,
            flags=1 if force else 0,
        )
        sent_at = time.monotonic()
        pending = PendingFrame(self._frame_sequence, sent_at, transform)
        self._pending_frame = pending
        try:
            await self.send_binary(packet)
        except Exception:
            self._pending_frame = None
            await self.disconnect()
            return False
        self._last_send_at = sent_at
        self.state.edge.last_frame_id = pending.frame_id
        return True

    def pop_latest_result(self) -> list[dict[str, Any]] | None:
        result = self._latest_result
        self._latest_result = None
        return result

    async def send_occupancy(self, counts: dict[int, int]) -> None:
        if not self.connected:
            return
        occupancy = {zone_id: count > 0 for zone_id, count in counts.items()}
        now = time.monotonic()
        changed = occupancy != self._last_occupancy
        if not changed and now - self._last_occupancy_send < self.settings.edge_occupancy_heartbeat_seconds:
            return
        try:
            await self.send_json({
                "type": "occupancy",
                "timestamp_us": time.time_ns() // 1_000,
                "configuration_revision": self.state.edge.configuration_revision,
                "zones": [
                    {"zone_id": zone_id, "occupied": occupied, "people_count": counts.get(zone_id, 0)}
                    for zone_id, occupied in sorted(occupancy.items())
                ],
            })
        except Exception:
            await self.disconnect()
            return
        self._last_occupancy = occupancy
        self._last_occupancy_send = now

    async def send_config(self, zones: list[dict[str, Any]], relays: list[dict[str, Any]], revision: int) -> None:
        if not self.connected:
            return
        await self.send_json({
            "type": "config",
            "revision": revision,
            "activation_delay_seconds": self.settings.activation_delay_seconds,
            "deactivation_delay_seconds": self.settings.deactivation_delay_seconds,
            "camera_loss_timeout_seconds": self.settings.camera_loss_safety_timeout,
            "confidence_threshold": self.settings.detection_confidence,
            "zones": zones,
            "relays": relays,
        })

    def bump_configuration_revision(self) -> int:
        self.state.edge.configuration_revision += 1
        return self.state.edge.configuration_revision

    async def send_current_config(self) -> None:
        if not self.connected:
            return
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from ..database import SessionLocal
        from ..models import Relay, Zone
        from .zone_service import ZoneService

        with SessionLocal() as db:
            zones = list(db.scalars(select(Zone).options(selectinload(Zone.mappings)).order_by(Zone.id)).all())
            relays = list(db.scalars(select(Relay).order_by(Relay.id)).all())
            zone_payload = [ZoneService.serialize(zone) for zone in zones]
            relay_payload = [
                {
                    "id": relay.id,
                    "gpio_pin": relay.gpio_pin,
                    "active_low": relay.active_low,
                }
                for relay in relays
            ]
        await self.send_config(zone_payload, relay_payload, self.state.edge.configuration_revision)

    def schedule_current_config(self) -> None:
        if not self.connected:
            return
        try:
            asyncio.get_running_loop().create_task(self._safe_send_current_config())
        except RuntimeError:
            return

    async def _safe_send_current_config(self) -> None:
        try:
            await self.send_current_config()
        except Exception:
            await self.disconnect()

    async def command(self, payload: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
        command_id = str(payload["command_id"])
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending_commands[command_id] = future
        try:
            await self.send_json(payload)
            return await asyncio.wait_for(future, timeout=timeout or self.settings.esp32_timeout_seconds)
        finally:
            self._pending_commands.pop(command_id, None)

    async def handle_text(self, text: str) -> None:
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            self.state.edge.protocol_errors += 1
            await self.send_json({"type": "error", "code": "invalid_json"})
            return
        if not isinstance(message, dict) or not isinstance(message.get("type"), str):
            self.state.edge.protocol_errors += 1
            return
        self.state.edge.last_seen_at = time.time()
        message_type = message["type"]
        if message_type == "hello":
            await self._handle_hello(message)
        elif message_type == "inference_result":
            self._handle_inference_result(message)
        elif message_type == "metrics":
            self._handle_metrics(message)
        elif message_type == "ack":
            self._handle_ack(message)
        elif message_type == "occupancy_state":
            self._handle_occupancy_state(message)
        elif message_type == "relay_event":
            self._handle_relay_event(message)
        elif message_type == "error":
            self.state.alert("error", str(message.get("message", "ESP32 edge error")))
        else:
            self.state.edge.protocol_errors += 1

    async def _handle_hello(self, message: dict[str, Any]) -> None:
        protocol = int(message.get("protocol", 0))
        input_width = int(message.get("input_width", 0))
        input_height = int(message.get("input_height", 0))
        model_sha256 = str(message.get("model_sha256", ""))
        expected_hash = self.settings.edge_expected_model_sha256.strip().lower()
        rejection = None
        if self.settings.app_env.lower() == "production" and not expected_hash:
            rejection = "Production requires EDGE_EXPECTED_MODEL_SHA256"
        elif protocol != 1:
            rejection = f"Unsupported edge protocol {protocol}"
        elif (input_width, input_height) != (self.settings.edge_input_width, self.settings.edge_input_height):
            rejection = f"Edge input {input_width}x{input_height} does not match configured 288x160"
        elif expected_hash and model_sha256.lower() != expected_hash:
            rejection = "ESP32 model SHA-256 does not match EDGE_EXPECTED_MODEL_SHA256"
        if rejection:
            self.state.detection.model_loaded = False
            self.state.detection.running = False
            self.state.detection.error = rejection
            self.state.alert("critical", rejection)
            await self.send_json({
                "type": "emergency",
                "active": True,
                "command_id": f"edge-reject-{time.time_ns()}",
                "reason": "model_or_protocol_mismatch",
            })
            websocket = self.websocket
            if websocket is not None:
                await websocket.close(code=1008, reason="edge identity rejected")
            await self.disconnect(websocket)
            return
        self.state.edge.device_id = str(message.get("device_id", "visualec-esp32-s3"))
        self.state.edge.firmware_version = str(message.get("firmware_version", "unknown"))
        self.state.edge.model_version = str(message.get("model_version", "unknown"))
        self.state.edge.model_sha256 = model_sha256
        self.state.edge.model_input_width = max(1, int(message.get("model_input_width", input_width)))
        self.state.edge.model_input_height = max(1, int(message.get("model_input_height", input_height)))
        self.state.edge.configuration_revision = int(message.get("configuration_revision", 0))
        self.state.detection.running = True
        self.state.detection.model_loaded = True
        self.state.detection.model_name = self.state.edge.model_version
        self.state.detection.provider = "ESP-DL INT8"
        self.state.detection.error = None
        await self.send_json({"type": "hello_ack", "protocol": 1, "server_time_us": time.time_ns() // 1_000})
        await self.send_current_config()

    def _handle_inference_result(self, message: dict[str, Any]) -> None:
        frame_id = int(message.get("frame_id", -1))
        pending = self._pending_frame
        if pending is None or pending.frame_id != frame_id:
            self.state.edge.late_results += 1
            return
        detections: list[dict[str, Any]] = []
        for item in message.get("detections", []):
            if not isinstance(item, dict) or not isinstance(item.get("bbox"), list) or len(item["bbox"]) != 4:
                continue
            bbox = restore_bbox([float(value) for value in item["bbox"]], pending.transform)
            if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                continue
            detections.append({
                "bbox": bbox,
                "confidence": round(float(item.get("confidence", 0.0)), 3),
                "tracking_id": None,
            })
        round_trip_ms = (time.monotonic() - pending.sent_at) * 1000
        self._pending_frame = None
        self._latest_result = detections
        inference_ms = float(message.get("inference_ms", 0.0))
        self.state.edge.inference_ms = round(inference_ms, 1)
        self.state.edge.round_trip_ms = round(round_trip_ms, 1)
        self.state.edge.inference_fps = round(1000 / inference_ms, 1) if inference_ms > 0 else 0.0
        self.state.edge.completed_frames += 1
        self.state.detection.inference_ms = self.state.edge.inference_ms
        self.state.detection.fps = self.state.edge.inference_fps
        self.state.detection.error = None

    def _handle_metrics(self, message: dict[str, Any]) -> None:
        self.state.edge.free_heap_bytes = int(message.get("free_heap_bytes", 0))
        self.state.edge.free_psram_bytes = int(message.get("free_psram_bytes", 0))
        self.state.edge.wifi_rssi = int(message.get("wifi_rssi", 0))
        self.state.edge.configuration_revision = int(message.get("configuration_revision", self.state.edge.configuration_revision))

    def _handle_ack(self, message: dict[str, Any]) -> None:
        command_id = str(message.get("command_id", ""))
        relay_id = message.get("relay_id")
        effective_state = message.get("effective_state", message.get("state"))
        if isinstance(relay_id, int) and effective_state in ("on", "off"):
            with self.state.lock:
                self.state.relays[relay_id] = effective_state == "on"
            self.state.edge.last_acknowledgement = command_id
        future = self._pending_commands.get(command_id)
        if future is not None and not future.done():
            future.set_result(message)

    def _handle_occupancy_state(self, message: dict[str, Any]) -> None:
        for item in message.get("zones", []):
            if not isinstance(item, dict):
                continue
            zone_id = item.get("zone_id")
            occupied = item.get("occupied")
            if not isinstance(zone_id, int) or not isinstance(occupied, bool) or zone_id not in self.state.zones:
                continue
            zone = self.state.zones[zone_id]
            previous = zone.occupied
            zone.occupied = occupied
            if occupied and not previous:
                zone.occupied_since = time.monotonic()
            elif previous and not occupied:
                zone.occupied_since = None
            if previous != occupied:
                self.state.record_event(
                    "occupancy",
                    f"{zone.name} became {'occupied' if occupied else 'vacant'}",
                    source="ESP32-S3",
                    status="occupied" if occupied else "vacant",
                    zone_id=zone_id,
                )

    def _handle_relay_event(self, message: dict[str, Any]) -> None:
        relay_id = message.get("relay_id")
        effective_state = message.get("effective_state")
        if not isinstance(relay_id, int) or effective_state not in ("on", "off"):
            self.state.edge.protocol_errors += 1
            return
        with self.state.lock:
            self.state.relays[relay_id] = effective_state == "on"
        self.state.record_event(
            "relay",
            f"Relay {relay_id} turned {effective_state}",
            source="ESP32-S3",
            status="acknowledged",
            relay_id=relay_id,
            state=effective_state,
            reason=message.get("reason", "edge_state_machine"),
        )
