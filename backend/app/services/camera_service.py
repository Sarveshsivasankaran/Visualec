import threading
import time
from collections.abc import Iterable

import cv2
import numpy as np

from ..config import Settings
from .state import RuntimeState, now_iso


class CameraService:
    def __init__(self, settings: Settings, state: RuntimeState) -> None:
        self.settings = settings
        self.state = state
        self._capture: cv2.VideoCapture | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._frame_lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._processed_frame: np.ndarray | None = None
        self._index = settings.camera_index
        self._width = settings.camera_width
        self._height = settings.camera_height

    @staticmethod
    def list_devices(max_devices: int = 6) -> list[dict]:
        devices = []
        for index in range(max_devices):
            capture = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if capture.isOpened():
                devices.append({"index": index, "name": f"Camera {index}", "available": True})
            capture.release()
        return devices

    def configure(self, index: int, width: int, height: int) -> None:
        was_running = self.state.camera.running
        if was_running:
            self.stop()
        self._index, self._width, self._height = index, width, height
        if was_running:
            self.start()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.state.camera.running = True
        self.state.camera.health = "starting"
        self._thread = threading.Thread(target=self._capture_loop, name="visualec-camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        if self._capture:
            self._capture.release()
        self._capture = None
        self.state.camera.running = False
        self.state.camera.connected = False
        self.state.camera.health = "stopped"

    def latest_frame(self, processed: bool = True) -> np.ndarray | None:
        with self._frame_lock:
            selected = self._processed_frame if processed and self._processed_frame is not None else self._frame
            return None if selected is None else selected.copy()

    def set_processed_frame(self, frame: np.ndarray) -> None:
        with self._frame_lock:
            self._processed_frame = frame.copy()

    def jpeg(self) -> bytes | None:
        frame = self.latest_frame()
        if frame is None:
            return None
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
        return encoded.tobytes() if ok else None

    def mjpeg(self) -> Iterable[bytes]:
        while self.state.camera.running:
            jpeg = self.jpeg()
            if jpeg:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(0.05)

    def _open(self) -> bool:
        capture = cv2.VideoCapture(self._index, cv2.CAP_DSHOW)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not capture.isOpened():
            capture.release()
            return False
        self._capture = capture
        return True

    def _capture_loop(self) -> None:
        connected = self._open()
        if not connected:
            self.state.camera.error = "Camera unavailable; reconnecting"
            self.state.camera.health = "error"
            self.state.alert("error", self.state.camera.error)
        frame_count, window_start = 0, time.monotonic()
        reconnect_at = time.monotonic() + 5
        while not self._stop.is_set():
            if not connected:
                if time.monotonic() >= reconnect_at:
                    connected = self._open()
                    reconnect_at = time.monotonic() + 5
                    if connected:
                        self.state.camera.error = None
                        self.state.alert("info", "Camera connected")
                if not connected:
                    self.state.camera.connected = False
                    self.state.camera.health = "reconnecting"
                    time.sleep(.1)
                    continue
            else:
                assert self._capture is not None
                ok, frame = self._capture.read()
                if not ok:
                    self._capture.release()
                    self._capture = None
                    connected = False
                    reconnect_at = time.monotonic() + 5
                    with self._frame_lock:
                        self._frame = None
                        self._processed_frame = None
                    self.state.camera.connected = False
                    self.state.camera.health = "reconnecting"
                    self.state.camera.error = "Camera disconnected; reconnecting"
                    self.state.alert("error", self.state.camera.error)
                    continue
            with self._frame_lock:
                self._frame = frame
            frame_count += 1
            elapsed = time.monotonic() - window_start
            if elapsed >= 1:
                self.state.camera.fps = round(frame_count / elapsed, 1)
                frame_count, window_start = 0, time.monotonic()
            self.state.camera.connected = True
            self.state.camera.health = "healthy"
            self.state.camera.last_frame_at = now_iso()
            self.state.camera.index = self._index
            self.state.camera.width = frame.shape[1]
            self.state.camera.height = frame.shape[0]
            time.sleep(max(0.001, 1 / self.settings.camera_fps))
