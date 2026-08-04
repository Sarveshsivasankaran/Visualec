import time
from dataclasses import dataclass

from ..config import Settings
from .state import RuntimeState


@dataclass
class OccupancyTransition:
    zone_id: int
    previous: bool
    current: bool


class OccupancyService:
    def __init__(self, settings: Settings, state: RuntimeState) -> None:
        self.state = state
        self.activation_delay = settings.activation_delay_seconds
        self.deactivation_delay = settings.deactivation_delay_seconds

    def update(self, counts: dict[int, int], now: float | None = None) -> list[OccupancyTransition]:
        timestamp = time.monotonic() if now is None else now
        transitions: list[OccupancyTransition] = []
        with self.state.lock:
            for zone_id, zone in self.state.zones.items():
                count = counts.get(zone_id, 0)
                zone.people_count = count
                previous = zone.occupied
                if count > 0:
                    zone.empty_since = None
                    zone.last_occupied_at = timestamp
                    if zone.first_detected_at is None:
                        zone.first_detected_at = timestamp
                    if not zone.occupied and timestamp - zone.first_detected_at >= self.activation_delay:
                        zone.occupied = True
                        zone.occupied_since = timestamp
                else:
                    zone.first_detected_at = None
                    if zone.empty_since is None:
                        zone.empty_since = timestamp
                    if zone.occupied and timestamp - zone.empty_since >= self.deactivation_delay:
                        zone.occupied = False
                        zone.occupied_since = None
                if previous != zone.occupied:
                    transitions.append(OccupancyTransition(zone_id, previous, zone.occupied))
        return transitions
