from typing import Any

import cv2

from ..config import Settings
from .state import RuntimeState


class DetectionService:
    def __init__(self, settings: Settings, state: RuntimeState) -> None:
        self.settings = settings
        self.state = state
        self.confidence = settings.detection_confidence
        self.interval_ms = settings.inference_interval_ms

    def start(self) -> None:
        self.state.detection.running = True

    def stop(self) -> None:
        self.state.detection.running = False

    def configure(self, confidence: float, interval_ms: int) -> None:
        self.confidence, self.interval_ms = confidence, interval_ms

    def infer(self, _frame: Any) -> list[dict[str, Any]]:
        """Reject legacy laptop inference instead of silently falling back to it."""
        raise RuntimeError(
            "Laptop inference is disabled. Connect the authenticated ESP32-S3 edge "
            "runtime at /ws/edge; production never substitutes local or synthetic detections."
        )

    @staticmethod
    def draw(frame: np.ndarray, detections: list[dict[str, Any]]) -> None:
        for detection in detections:
            x1, y1, x2, y2 = map(int, detection["bbox"])
            cv2.rectangle(frame, (x1, y1), (x2, y2), (54, 211, 153), 2)
            label = f"person {detection['confidence']:.0%}"
            cv2.putText(frame, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, .55, (54, 211, 153), 2)
            cv2.circle(frame, ((x1 + x2) // 2, y2), 5, (0, 255, 255), -1)
