import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ..config import Settings
from .state import RuntimeState


class DetectionService:
    def __init__(self, settings: Settings, state: RuntimeState) -> None:
        self.settings = settings
        self.state = state
        self._model: Any = None
        self.confidence = settings.detection_confidence
        self.interval_ms = settings.inference_interval_ms

    def start(self) -> None:
        self.state.detection.running = True

    def stop(self) -> None:
        self.state.detection.running = False

    def configure(self, confidence: float, interval_ms: int) -> None:
        self.confidence, self.interval_ms = confidence, interval_ms

    def _load_model(self) -> None:
        if self._model is not None:
            return
        try:
            model_path = Path(self.settings.detection_model)
            if model_path.suffix.lower() == ".onnx":
                import onnxruntime as ort

                available = ort.get_available_providers()
                providers = ["DmlExecutionProvider", "CPUExecutionProvider"] if "DmlExecutionProvider" in available else ["CPUExecutionProvider"]
                options = ort.SessionOptions()
                options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                session = ort.InferenceSession(str(model_path), sess_options=options, providers=providers)
                self._model = session
                self.state.detection.model_loaded = True
                self.state.detection.model_name = self.settings.detection_model
                self.state.detection.provider = session.get_providers()[0]
                self.state.record_event(
                    "detection",
                    f"Person detector ready via {self.state.detection.provider}",
                    source=self.settings.detection_model,
                    status="online",
                )
                return
            from ultralytics import YOLO

            self._model = YOLO(self.settings.detection_model)
            self.state.detection.model_loaded = True
            self.state.detection.model_name = self.settings.detection_model
            self.state.detection.provider = "Ultralytics"
            self.state.record_event(
                "detection",
                "Person detector ready via Ultralytics",
                source=self.settings.detection_model,
                status="online",
            )
        except Exception as exc:
            self.state.detection.error = f"YOLO unavailable: {exc}"
            self.state.detection.model_loaded = False
            self.state.detection.running = False
            self.state.alert("critical", self.state.detection.error)
            self._model = False

    def infer(self, frame: np.ndarray) -> list[dict[str, Any]]:
        if not self.state.detection.running:
            return []
        self._load_model()
        if self._model is False:
            return []
        started = time.perf_counter()
        if self.settings.detection_model.lower().endswith(".onnx"):
            detections = self._infer_onnx(frame)
            elapsed = (time.perf_counter() - started) * 1000
            self.state.detection.inference_ms = round(elapsed, 1)
            self.state.detection.fps = round(1000 / elapsed, 1) if elapsed else 0
            return detections
        results = self._model.predict(
            frame,
            classes=[0],
            conf=self.confidence,
            verbose=False,
            imgsz=self.settings.detection_input_size,
        )
        detections: list[dict[str, Any]] = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = [float(value) for value in box.xyxy[0].tolist()]
                tracking_id = int(box.id[0]) if box.id is not None else None
                detections.append({
                    "bbox": [x1, y1, x2, y2],
                    "confidence": round(float(box.conf[0]), 3),
                    "tracking_id": tracking_id,
                })
        elapsed = (time.perf_counter() - started) * 1000
        self.state.detection.inference_ms = round(elapsed, 1)
        self.state.detection.fps = round(1000 / elapsed, 1) if elapsed else 0
        return detections

    def _infer_onnx(self, frame: np.ndarray) -> list[dict[str, Any]]:
        size = self.settings.detection_input_size
        height, width = frame.shape[:2]
        scale = min(size / width, size / height)
        resized_width, resized_height = round(width * scale), round(height * scale)
        resized = cv2.resize(frame, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((size, size, 3), 114, dtype=np.uint8)
        pad_x, pad_y = (size - resized_width) // 2, (size - resized_height) // 2
        canvas[pad_y:pad_y + resized_height, pad_x:pad_x + resized_width] = resized
        tensor = np.ascontiguousarray(canvas[:, :, ::-1].transpose(2, 0, 1), dtype=np.float32) / 255.0
        session = self._model
        output = session.run(None, {session.get_inputs()[0].name: tensor[None]})[0].squeeze(0)
        predictions = output.T if output.shape[0] < output.shape[1] else output
        scores = predictions[:, 4]
        candidates = predictions[scores >= self.confidence]
        if not len(candidates):
            return []
        scores = candidates[:, 4]
        boxes_xywh = candidates[:, :4]
        boxes_for_nms = [
            [float(cx - box_width / 2), float(cy - box_height / 2), float(box_width), float(box_height)]
            for cx, cy, box_width, box_height in boxes_xywh
        ]
        indices = cv2.dnn.NMSBoxes(boxes_for_nms, scores.tolist(), self.confidence, 0.45)
        detections: list[dict[str, Any]] = []
        for index in np.array(indices).reshape(-1):
            x, y, box_width, box_height = boxes_for_nms[int(index)]
            x1 = max(0.0, (x - pad_x) / scale)
            y1 = max(0.0, (y - pad_y) / scale)
            x2 = min(float(width), (x + box_width - pad_x) / scale)
            y2 = min(float(height), (y + box_height - pad_y) / scale)
            if x2 > x1 and y2 > y1:
                detections.append({
                    "bbox": [x1, y1, x2, y2],
                    "confidence": round(float(scores[int(index)]), 3),
                    "tracking_id": None,
                })
        return detections

    @staticmethod
    def draw(frame: np.ndarray, detections: list[dict[str, Any]]) -> None:
        for detection in detections:
            x1, y1, x2, y2 = map(int, detection["bbox"])
            cv2.rectangle(frame, (x1, y1), (x2, y2), (54, 211, 153), 2)
            label = f"person {detection['confidence']:.0%}"
            cv2.putText(frame, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, .55, (54, 211, 153), 2)
            cv2.circle(frame, ((x1 + x2) // 2, y2), 5, (0, 255, 255), -1)
