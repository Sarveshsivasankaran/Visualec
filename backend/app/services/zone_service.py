from collections.abc import Sequence
from typing import Any

import cv2
import numpy as np
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select

from ..models import Relay, Zone, ZoneRelayMapping
from .state import RuntimeState, ZoneRuntime


DEFAULT_COLOURS = ["#22d3ee", "#34d399", "#f59e0b"]


def point_in_polygon(point: tuple[float, float], polygon: Sequence[tuple[float, float]]) -> bool:
    """Ray-casting point inclusion; boundary points are treated as inside."""
    x, y = point
    inside = False
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        if abs(cross) < 1e-9 and min(x1, x2) - 1e-9 <= x <= max(x1, x2) + 1e-9 and min(y1, y2) - 1e-9 <= y <= max(y1, y2) + 1e-9:
            return True
        if (y1 > y) != (y2 > y):
            intersection_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x <= intersection_x:
                inside = not inside
    return inside


def bottom_centre(bbox: Sequence[float], width: int, height: int) -> tuple[float, float]:
    x1, _y1, x2, y2 = bbox
    return ((x1 + x2) / 2 / width, y2 / height)


class ZoneService:
    def __init__(self, state: RuntimeState) -> None:
        self.state = state

    @staticmethod
    def seed_defaults(db: Session) -> None:
        if db.scalar(select(Zone.id).limit(1)) is not None:
            return
        pins = [4, 5, 6]
        relays = [Relay(id=i + 1, name=f"Zone {i + 1} prototype load", gpio_pin=pins[i], rated_wattage=9) for i in range(3)]
        db.add_all(relays)
        for index in range(3):
            left, right = index / 3, (index + 1) / 3
            zone = Zone(
                id=index + 1,
                name=f"Zone {index + 1}",
                coordinates=[{"x": left, "y": 0}, {"x": right, "y": 0}, {"x": right, "y": 1}, {"x": left, "y": 1}],
                zone_type="rectangle",
                colour=DEFAULT_COLOURS[index],
            )
            db.add(zone)
            db.flush()
            db.add(ZoneRelayMapping(zone_id=zone.id, relay_id=relays[index].id, auto_control_enabled=True))
        db.commit()

    def reload(self, db: Session) -> None:
        zones = db.scalars(select(Zone).options(selectinload(Zone.mappings))).all()
        relays = db.scalars(select(Relay)).all()
        with self.state.lock:
            previous = self.state.zones
            self.state.zones = {
                zone.id: ZoneRuntime(
                    id=zone.id,
                    name=zone.name,
                    colour=zone.colour,
                    occupied=previous.get(zone.id, ZoneRuntime(zone.id, zone.name, zone.colour)).occupied,
                    relay_ids=[mapping.relay_id for mapping in zone.mappings],
                    auto_control_enabled=all(mapping.auto_control_enabled for mapping in zone.mappings),
                )
                for zone in zones if zone.enabled
            }
            self.state.relays = {relay.id: relay.state for relay in relays}
            self.state.relay_names = {relay.id: relay.name for relay in relays}
            self.state.relay_wattages = {relay.id: relay.rated_wattage for relay in relays}

    @staticmethod
    def serialize(zone: Zone) -> dict[str, Any]:
        return {
            "id": zone.id, "name": zone.name, "coordinates": zone.coordinates,
            "zone_type": zone.zone_type, "colour": zone.colour, "enabled": zone.enabled,
            "relay_ids": [mapping.relay_id for mapping in zone.mappings],
            "auto_control_enabled": all(mapping.auto_control_enabled for mapping in zone.mappings),
        }

    @staticmethod
    def assign(detections: list[dict[str, Any]], zones: Sequence[Zone], width: int, height: int) -> dict[int, list[dict[str, Any]]]:
        assignments = {zone.id: [] for zone in zones if zone.enabled}
        for detection in detections:
            point = bottom_centre(detection["bbox"], width, height)
            for zone in zones:
                polygon = [(float(item["x"]), float(item["y"])) for item in zone.coordinates]
                if zone.enabled and point_in_polygon(point, polygon):
                    assignments[zone.id].append(detection)
                    detection["zone_id"] = zone.id
                    break
        return assignments

    @staticmethod
    def draw(frame: np.ndarray, zones: Sequence[Zone]) -> None:
        height, width = frame.shape[:2]
        overlay = frame.copy()
        for zone in zones:
            if not zone.enabled:
                continue
            points = np.array([(int(p["x"] * width), int(p["y"] * height)) for p in zone.coordinates], dtype=np.int32)
            colour = tuple(int(zone.colour[index:index + 2], 16) for index in (5, 3, 1))
            cv2.polylines(frame, [points], True, colour, 2)
            cv2.fillPoly(overlay, [points], colour)
            anchor = tuple(points[0])
            cv2.putText(frame, zone.name, (anchor[0] + 10, anchor[1] + 26), cv2.FONT_HERSHEY_SIMPLEX, .7, colour, 2)
        cv2.addWeighted(overlay, .08, frame, .92, 0, frame)
