# Visualec backend

From this directory, create a Python 3.11+ environment, install `requirements.txt`, copy `.env.example` to `.env`, and run:

```bash
uvicorn app.main:app --reload
```

Swagger UI is available at `http://localhost:8000/docs`. A physical webcam and reachable ESP32-S3 are required. Configure `CAMERA_INDEX` and `ESP32_BASE_URL`; missing devices remain visibly offline and relay commands are not acknowledged locally.

Apply the initial database migration with `alembic upgrade head`. Development startup also creates missing tables defensively.

The standalone Phase 1 OpenCV window runs with `python run_phase1.py`; press `q` to close it.

For Windows GPU acceleration, export once with `python -c "from ultralytics import YOLO; YOLO('yolov8n.pt').export(format='onnx', imgsz=320)"`, then set `DETECTION_MODEL=yolov8n.onnx`. The backend selects DirectML when the provider is available and otherwise uses the ONNX CPU provider.
