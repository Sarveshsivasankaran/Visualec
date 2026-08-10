import asyncio
import logging
import time

from sqlalchemy import select

from ..database import SessionLocal
from ..models import DetectionEvent, OccupancyEvent, Zone
from .camera_service import CameraService
from .detection_service import DetectionService
from .energy_service import EnergyService
from .occupancy_service import OccupancyService
from .relay_service import RelayService
from .state import RuntimeState
from .tracking_service import TrackingService
from .websocket_manager import WebSocketManager
from .zone_service import ZoneService

logger = logging.getLogger("visualec.runtime")


class VisualecRuntime:
    def __init__(
        self,
        state: RuntimeState,
        camera: CameraService,
        detector: DetectionService,
        zones: ZoneService,
        occupancy: OccupancyService,
        relays: RelayService,
        energy: EnergyService,
        websockets: WebSocketManager,
    ) -> None:
        self.state, self.camera, self.detector, self.zones = state, camera, detector, zones
        self.occupancy, self.relays, self.energy, self.websockets = occupancy, relays, energy, websockets
        self.tracker = TrackingService()
        self._camera_lost_at: float | None = None
        self._task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last_people_count = 0

    def start(self) -> None:
        self.detector.start()
        self._task = asyncio.create_task(self._loop(), name="visualec-runtime")
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name="visualec-esp32-heartbeat")

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
        while not self._stop.is_set():
            now = time.monotonic()
            frame = self.camera.latest_frame(processed=False) if self.state.camera.running else None
            with SessionLocal() as db:
                if frame is None:
                    if self._camera_lost_at is None:
                        self._camera_lost_at = now
                    transitions = []
                    if (
                        self.camera.settings.camera_loss_action == "off"
                        and now - self._camera_lost_at >= self.camera.settings.camera_loss_safety_timeout
                    ):
                        transitions = self.occupancy.update({zone_id: 0 for zone_id in self.state.zones})
                    for transition in transitions:
                        db.add(OccupancyEvent(zone_id=transition.zone_id, previous_state=transition.previous, new_state=transition.current))
                    db.commit()
                    try:
                        await self.relays.reconcile_automatic(
                            db,
                            self.occupancy.activation_delay,
                            self.occupancy.deactivation_delay,
                        )
                    except Exception as exc:
                        self.state.alert("error", str(exc))
                    payload = self.state.snapshot()
                    payload["energy"] = self.energy.summary(db)
                    await self.websockets.broadcast(payload)
                    await asyncio.sleep(.25)
                    continue
                self._camera_lost_at = None
                zones = db.scalars(select(Zone)).all()
                detections = self.tracker.update(await asyncio.to_thread(self.detector.infer, frame))
                assignments = self.zones.assign(detections, zones, frame.shape[1], frame.shape[0])
                counts = {zone_id: len(items) for zone_id, items in assignments.items()}
                transitions = self.occupancy.update(counts)
                self.state.detection.detections = detections
                self.state.detection.people_count = len(detections)
                if len(detections) != self._last_people_count:
                    self.state.record_event(
                        "detection",
                        f"People in frame changed from {self._last_people_count} to {len(detections)}",
                        source="YOLO",
                        status="live",
                        people_count=len(detections),
                    )
                    self._last_people_count = len(detections)
                self.zones.draw(frame, zones)
                self.detector.draw(frame, detections)
                self.camera.set_processed_frame(frame)
                for transition in transitions:
                    db.add(OccupancyEvent(zone_id=transition.zone_id, previous_state=transition.previous, new_state=transition.current))
                    logger.info("occupancy_transition", extra={"zone_id": transition.zone_id, "occupied": transition.current})
                    zone_name = self.state.zones[transition.zone_id].name
                    self.state.record_event(
                        "occupancy",
                        f"{zone_name} became {'occupied' if transition.current else 'vacant'}",
                        source=zone_name,
                        status="occupied" if transition.current else "vacant",
                        zone_id=transition.zone_id,
                    )
                if detections:
                    for detection in detections:
                        db.add(DetectionEvent(
                            people_count=len(detections), zone_id=detection.get("zone_id"),
                            confidence=detection["confidence"], tracking_id=detection.get("tracking_id"),
                        ))
                db.commit()
                try:
                    await self.relays.reconcile_automatic(
                        db,
                        self.occupancy.activation_delay,
                        self.occupancy.deactivation_delay,
                    )
                except Exception as exc:
                    self.state.alert("error", str(exc))
                payload = self.state.snapshot()
                payload["energy"] = self.energy.summary(db)
                await self.websockets.broadcast(payload)
            await asyncio.sleep(self.detector.interval_ms / 1000)
