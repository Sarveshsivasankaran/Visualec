from fastapi import APIRouter, Request

from ..schemas import DetectionSettings

router = APIRouter(prefix="/api/detection", tags=["detection"])


@router.get("/status")
def status(request: Request) -> dict:
    return request.app.state.runtime_state.snapshot()["detection"]


@router.post("/start")
def start(request: Request) -> dict:
    request.app.state.detector.start()
    return {"success": True, "running": True}


@router.post("/stop")
def stop(request: Request) -> dict:
    request.app.state.detector.stop()
    return {"success": True, "running": False}


@router.put("/settings")
def settings(payload: DetectionSettings, request: Request) -> dict:
    request.app.state.detector.configure(payload.confidence, payload.inference_interval_ms)
    return {"success": True, **payload.model_dump()}


@router.get("/latest")
def latest(request: Request) -> dict:
    state = request.app.state.runtime_state
    return {"people_count": state.detection.people_count, "detections": state.detection.detections}
