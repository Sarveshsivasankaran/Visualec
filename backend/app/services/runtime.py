from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy import select

from ..database import SessionLocal
from ..models import DetectionEvent, Zone
from .camera_service import CameraService
from .detection_service import DetectionService
from .edge_inference_service import EdgeInferenceService
from .energy_service import EnergyService
from .occupancy_service import OccupancyService
from .relay_service import RelayService
from .state import RuntimeState
from .tracking_service import TrackingService
from .websocket_manager import WebSocketManager
from .zone_service import ZoneService

logger = logging.getLogger("visualec.runtime")


class VisualecRuntime:
    """Runs camera-rate tracking while the ESP32 asynchronously handles sparse inference."""

    def __init__(
        self,
        state: RuntimeState,
        camera: CameraService,
        detector: DetectionService,
        edge: EdgeInferenceService,
        zones: ZoneService,
        occupancy: OccupancyService,
        relays: RelayService,
        energy: EnergyService,
        websockets: WebSocketManager,
    ) -> None:
        self.state, self.camera, self.detector, self.edge, self.zones = state, camera, detector, edge, zones
        self.occupancy, self.relays, self.energy, self.websockets = occupancy, relays, energy, websockets
        self.tracker = TrackingService(max_age_seconds=0.75)
        self._task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last_people_count = 0

    def start(self) -> None:
        self.detector.start()
        self.state.detection.provider = "ESP-DL INT8"
        self.state.detection.error = "Waiting for ESP32-S3 edge inference"
        self._task = asyncio.create_task(self._loop(), name="visualec-camera-tracking")
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name="visualec-edge-heartbeat")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task
        if self._heartbeat_task:
            await self._heartbeat_task

    async def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            await self.relays.check_health()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=2)
            except TimeoutError:
                pass

    async def _loop(self) -> None:
        target_period = 1 / max(1, self.camera.settings.camera_fps)
        while not self._stop.is_set():
            loop_started = time.monotonic()
            frame = self.camera.latest_frame(processed=False) if self.state.camera.running else None
            if frame is None:
                self.state.detection.people_count = 0
                self.state.detection.detections = []
                payload = self.state.snapshot()
                with SessionLocal() as db:
                    payload["energy"] = self.energy.summary(db)
                await self.websockets.broadcast(payload)
                await asyncio.sleep(.1)
                continue

            motion_score = self.edge.motion_score(frame)
            edge_result = self.edge.pop_latest_result()
            if edge_result:
                detections = self.tracker.update(edge_result, frame=frame, now=loop_started)
            else:
                detections = self.tracker.advance(frame, now=loop_started)
            await self.edge.maybe_send_frame(frame, motion_score, force=self.tracker.uncertain and bool(detections))

            with SessionLocal() as db:
                zones = list(db.scalars(select(Zone).order_by(Zone.id)).all())
                assignments = self.zones.assign(detections, zones, frame.shape[1], frame.shape[0])
                counts = {zone_id: len(items) for zone_id, items in assignments.items()}
                with self.state.lock:
                    for zone_id, zone in self.state.zones.items():
                        zone.people_count = counts.get(zone_id, 0)
                        zone.raw_occupied = zone.people_count > 0
                await self.edge.send_occupancy(counts)
                self.state.detection.detections = detections
                self.state.detection.people_count = len(detections)
                if len(detections) != self._last_people_count:
                    self.state.record_event(
                        "detection",
                        f"Tracked people changed from {self._last_people_count} to {len(detections)}",
                        source="ESP-DL + temporal tracker",
                        status="live",
                        people_count=len(detections),
                    )
                    self._last_people_count = len(detections)
                self.zones.draw(frame, zones)
                self.detector.draw(frame, detections)
                self.camera.set_processed_frame(frame)
                if edge_result:
                    for detection in edge_result:
                        db.add(DetectionEvent(
                            people_count=len(edge_result),
                            zone_id=detection.get("zone_id"),
                            confidence=detection["confidence"],
                            tracking_id=detection.get("tracking_id"),
                        ))
                    db.commit()
                payload = self.state.snapshot()
                payload["energy"] = self.energy.summary(db)
            await self.websockets.broadcast(payload)
            elapsed = time.monotonic() - loop_started
            await asyncio.sleep(max(0.001, target_period - elapsed))
