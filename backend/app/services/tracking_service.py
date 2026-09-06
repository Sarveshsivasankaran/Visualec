from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np


def iou(a: list[float], b: list[float]) -> float:
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, right - left) * max(0, bottom - top)
    area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    return intersection / (area_a + area_b - intersection) if area_a + area_b > intersection else 0


@dataclass
class Track:
    tracking_id: int
    bbox: list[float]
    confidence: float
    last_detected: float
    last_updated: float
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    points: np.ndarray | None = None


class TrackingService:
    """Detector-corrected optical-flow tracker for 24 Hz output between edge results."""

    def __init__(self, max_age_seconds: float = 0.75, match_iou: float = 0.25) -> None:
        self.max_age_seconds = max_age_seconds
        self.match_iou = match_iou
        self._next_id = 1
        self._tracks: dict[int, Track] = {}
        self._previous_gray: np.ndarray | None = None
        self.uncertain = True

    def _expire(self, timestamp: float) -> None:
        self._tracks = {
            track_id: track
            for track_id, track in self._tracks.items()
            if timestamp - track.last_detected <= self.max_age_seconds
        }

    @staticmethod
    def _gray(frame: np.ndarray) -> np.ndarray:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    @staticmethod
    def _seed_points(gray: np.ndarray, bbox: list[float]) -> np.ndarray | None:
        height, width = gray.shape
        x1, y1, x2, y2 = [int(round(value)) for value in bbox]
        x1, x2 = max(0, min(width - 1, x1)), max(0, min(width, x2))
        y1, y2 = max(0, min(height - 1, y1)), max(0, min(height, y2))
        if x2 - x1 < 4 or y2 - y1 < 4:
            return None
        mask = np.zeros_like(gray)
        mask[y1:y2, x1:x2] = 255
        return cv2.goodFeaturesToTrack(gray, mask=mask, maxCorners=24, qualityLevel=0.01, minDistance=5)

    def update(
        self,
        detections: list[dict[str, Any]],
        frame: np.ndarray | None = None,
        now: float | None = None,
    ) -> list[dict[str, Any]]:
        timestamp = time.monotonic() if now is None else now
        self._expire(timestamp)
        available = set(self._tracks)
        gray = self._gray(frame) if frame is not None else None
        for detection in detections:
            bbox = [float(value) for value in detection["bbox"]]
            supplied_id = detection.get("tracking_id")
            if supplied_id is not None:
                track_id = int(supplied_id)
            else:
                matches = [(iou(bbox, self._tracks[item].bbox), item) for item in available]
                score, track_id = max(matches, default=(0.0, -1))
                if score < self.match_iou:
                    track_id = self._next_id
                    self._next_id += 1
                else:
                    available.remove(track_id)
                detection["tracking_id"] = track_id
            previous = self._tracks.get(track_id)
            velocity_x = velocity_y = 0.0
            if previous is not None:
                elapsed = max(0.001, timestamp - previous.last_updated)
                previous_centre_x = (previous.bbox[0] + previous.bbox[2]) / 2
                previous_centre_y = (previous.bbox[1] + previous.bbox[3]) / 2
                velocity_x = (((bbox[0] + bbox[2]) / 2) - previous_centre_x) / elapsed
                velocity_y = (((bbox[1] + bbox[3]) / 2) - previous_centre_y) / elapsed
            self._tracks[track_id] = Track(
                tracking_id=track_id,
                bbox=bbox,
                confidence=float(detection.get("confidence", 0.0)),
                last_detected=timestamp,
                last_updated=timestamp,
                velocity_x=velocity_x,
                velocity_y=velocity_y,
                points=self._seed_points(gray, bbox) if gray is not None else None,
            )
        if gray is not None:
            self._previous_gray = gray
        self.uncertain = not detections
        return detections

    def advance(self, frame: np.ndarray, now: float | None = None) -> list[dict[str, Any]]:
        timestamp = time.monotonic() if now is None else now
        self._expire(timestamp)
        gray = self._gray(frame)
        height, width = gray.shape
        any_uncertain = not self._tracks
        for track in self._tracks.values():
            elapsed = max(0.0, timestamp - track.last_updated)
            moved = False
            if self._previous_gray is not None and track.points is not None and len(track.points) >= 3:
                next_points, status, _errors = cv2.calcOpticalFlowPyrLK(
                    self._previous_gray,
                    gray,
                    track.points,
                    None,
                    winSize=(21, 21),
                    maxLevel=2,
                    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03),
                )
                if next_points is not None and status is not None:
                    valid = status.reshape(-1) == 1
                    old_valid = track.points.reshape(-1, 2)[valid]
                    new_valid = next_points.reshape(-1, 2)[valid]
                    if len(new_valid) >= 3:
                        delta = np.median(new_valid - old_valid, axis=0)
                        dx, dy = float(delta[0]), float(delta[1])
                        track.bbox = [track.bbox[0] + dx, track.bbox[1] + dy, track.bbox[2] + dx, track.bbox[3] + dy]
                        track.points = new_valid.reshape(-1, 1, 2).astype(np.float32)
                        moved = True
            if not moved and elapsed > 0:
                dx, dy = track.velocity_x * elapsed, track.velocity_y * elapsed
                track.bbox = [track.bbox[0] + dx, track.bbox[1] + dy, track.bbox[2] + dx, track.bbox[3] + dy]
                any_uncertain = True
            track.bbox[0] = min(max(track.bbox[0], 0.0), float(width))
            track.bbox[2] = min(max(track.bbox[2], 0.0), float(width))
            track.bbox[1] = min(max(track.bbox[1], 0.0), float(height))
            track.bbox[3] = min(max(track.bbox[3], 0.0), float(height))
            track.last_updated = timestamp
            if timestamp - track.last_detected > 0.4 or track.points is None or len(track.points) < 3:
                any_uncertain = True
        self._previous_gray = gray
        self.uncertain = any_uncertain
        return [
            {
                "bbox": track.bbox.copy(),
                "confidence": round(track.confidence, 3),
                "tracking_id": track.tracking_id,
                "predicted": timestamp > track.last_detected,
            }
            for track in self._tracks.values()
            if track.bbox[2] > track.bbox[0] and track.bbox[3] > track.bbox[1]
        ]
