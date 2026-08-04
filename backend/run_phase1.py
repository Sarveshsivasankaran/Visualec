"""Single-command real-time computer-vision zone monitor."""
import time

import cv2

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.services.camera_service import CameraService
from app.services.detection_service import DetectionService
from app.services.occupancy_service import OccupancyService
from app.services.state import RuntimeState, ZoneRuntime


def main() -> None:
    settings = get_settings()
    Base.metadata.create_all(engine)
    state = RuntimeState()
    for index, colour in enumerate(("#22d3ee", "#34d399", "#f59e0b"), 1):
        state.zones[index] = ZoneRuntime(index, f"Zone {index}", colour, relay_ids=[index])
    camera = CameraService(settings, state)
    detector = DetectionService(settings, state)
    occupancy = OccupancyService(settings, state)
    camera.start()
    detector.start()
    print('{"event":"phase1_started","quit_key":"q"}')
    try:
        while True:
            frame = camera.latest_frame(False)
            if frame is None:
                time.sleep(.05)
                continue
            detections = detector.infer(frame)
            counts = {1: 0, 2: 0, 3: 0}
            for item in detections:
                x1, _y1, x2, _y2 = item["bbox"]
                counts[min(3, int(((x1 + x2) / 2) / frame.shape[1] * 3) + 1)] += 1
            transitions = occupancy.update(counts)
            for event in transitions:
                print(f'{{"event":"occupancy","zone":{event.zone_id},"occupied":{str(event.current).lower()}}}')
            detector.draw(frame, detections)
            for index in range(1, 3):
                cv2.line(frame, (frame.shape[1] * index // 3, 0), (frame.shape[1] * index // 3, frame.shape[0]), (255, 255, 0), 2)
            for index in range(1, 4):
                cv2.putText(frame, f"Zone {index}: {counts[index]} people", (20 + (index - 1) * frame.shape[1] // 3, 35), cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 255, 0), 2)
            cv2.imshow("Visualec Phase 1", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        detector.stop()
        camera.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
