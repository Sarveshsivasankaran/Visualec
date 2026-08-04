import time
from typing import Any


def iou(a: list[float], b: list[float]) -> float:
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, right - left) * max(0, bottom - top)
    area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    return intersection / (area_a + area_b - intersection) if area_a + area_b > intersection else 0


class TrackingService:
    """Lightweight IoU tracker that supplies stable IDs between detector frames."""

    def __init__(self, max_age_seconds: float = 1.5, match_iou: float = 0.25) -> None:
        self.max_age_seconds = max_age_seconds
        self.match_iou = match_iou
        self._next_id = 1
        self._tracks: dict[int, tuple[list[float], float]] = {}

    def update(self, detections: list[dict[str, Any]], now: float | None = None) -> list[dict[str, Any]]:
        timestamp = time.monotonic() if now is None else now
        self._tracks = {track_id: value for track_id, value in self._tracks.items() if timestamp - value[1] <= self.max_age_seconds}
        available = set(self._tracks)
        for detection in detections:
            if detection.get("tracking_id") is not None:
                track_id = int(detection["tracking_id"])
            else:
                matches = [(iou(detection["bbox"], self._tracks[item][0]), item) for item in available]
                score, track_id = max(matches, default=(0.0, -1))
                if score < self.match_iou:
                    track_id = self._next_id
                    self._next_id += 1
                else:
                    available.remove(track_id)
                detection["tracking_id"] = track_id
            self._tracks[track_id] = (detection["bbox"], timestamp)
        return detections
