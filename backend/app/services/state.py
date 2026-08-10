from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import RLock
import time
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CameraState:
    connected: bool = False
    running: bool = False
    health: str = "stopped"
    fps: float = 0.0
    index: int = 0
    width: int = 1280
    height: int = 720
    last_frame_at: str | None = None
    error: str | None = None


@dataclass
class DetectionState:
    running: bool = False
    model_loaded: bool = False
    model_name: str = "yolov8n.pt"
    provider: str = "unloaded"
    people_count: int = 0
    inference_ms: float = 0.0
    fps: float = 0.0
    detections: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


@dataclass
class ZoneRuntime:
    id: int
    name: str
    colour: str
    occupied: bool = False
    people_count: int = 0
    first_detected_at: float | None = None
    empty_since: float | None = None
    occupied_since: float | None = None
    last_occupied_at: float | None = None
    relay_ids: list[int] = field(default_factory=list)
    auto_control_enabled: bool = True


class RuntimeState:
    def __init__(self) -> None:
        self.lock = RLock()
        self.camera = CameraState()
        self.detection = DetectionState()
        self.zones: dict[int, ZoneRuntime] = {}
        self.relays: dict[int, bool] = {}
        self.relay_names: dict[int, str] = {}
        self.relay_wattages: dict[int, float] = {}
        self.manual_overrides: dict[int, tuple[bool, float]] = {}
        self.mode = "automatic"
        self.emergency = False
        self.esp32_connected = False
        self.started_at = datetime.now(timezone.utc)
        self.alerts: list[dict[str, str]] = []
        self.events: list[dict[str, Any]] = []
        self._event_sequence = 0

    def record_event(
        self,
        event_type: str,
        message: str,
        source: str = "runtime",
        status: str = "info",
        **details: Any,
    ) -> None:
        with self.lock:
            self._event_sequence += 1
            self.events.insert(0, {
                "id": self._event_sequence,
                "timestamp": now_iso(),
                "type": event_type,
                "message": message,
                "source": source,
                "status": status,
                "details": details,
            })
            del self.events[15:]

    def alert(self, level: str, message: str) -> None:
        with self.lock:
            self.alerts.insert(0, {"timestamp": now_iso(), "level": level, "message": message})
            del self.alerts[20:]
        self.record_event("system", message, status=level)

    def snapshot(self) -> dict[str, Any]:
        now_monotonic = time.monotonic()
        with self.lock:
            zones = []
            for zone in self.zones.values():
                payload = asdict(zone)
                payload["occupancy_duration_seconds"] = (
                    max(0.0, now_monotonic - zone.occupied_since) if zone.occupied and zone.occupied_since else 0.0
                )
                zones.append(payload)
            return {
                "type": "system_update",
                "timestamp": now_iso(),
                "camera": asdict(self.camera),
                "detection": asdict(self.detection),
                "zones": zones,
                "relays": [
                    {
                        "id": relay_id,
                        "name": self.relay_names.get(relay_id, f"Relay {relay_id}"),
                        "state": "on" if state else "off",
                        "rated_wattage": self.relay_wattages.get(relay_id, 0),
                        "manual_override": relay_id in self.manual_overrides and self.manual_overrides[relay_id][1] > now_monotonic,
                        "manual_override_remaining_seconds": max(
                            0.0,
                            self.manual_overrides[relay_id][1] - now_monotonic,
                        ) if relay_id in self.manual_overrides else 0.0,
                    }
                    for relay_id, state in sorted(self.relays.items())
                ],
                "esp32": {"connected": self.esp32_connected},
                "mode": self.mode,
                "emergency": self.emergency,
                "alerts": self.alerts[:5],
                "events": self.events[:15],
            }
