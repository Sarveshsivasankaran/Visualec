from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from ..schemas import CameraSelect

router = APIRouter(prefix="/api/camera", tags=["camera"])


@router.get("/devices")
async def devices(request: Request) -> list[dict]:
    return await __import__("asyncio").to_thread(request.app.state.camera.list_devices)


@router.get("/status")
def status(request: Request) -> dict:
    return request.app.state.runtime_state.snapshot()["camera"]


@router.post("/start")
def start(request: Request) -> dict:
    request.app.state.camera.start()
    return {"success": True, "status": "starting"}


@router.post("/stop")
def stop(request: Request) -> dict:
    request.app.state.camera.stop()
    return {"success": True, "status": "stopped"}


@router.post("/select")
def select_camera(payload: CameraSelect, request: Request) -> dict:
    request.app.state.camera.configure(payload.index, payload.width, payload.height)
    return {"success": True, **payload.model_dump()}


@router.get("/frame")
def frame(request: Request) -> Response:
    data = request.app.state.camera.jpeg()
    if data is None:
        raise HTTPException(503, "No camera frame is available")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/stream")
def stream(request: Request) -> StreamingResponse:
    return StreamingResponse(request.app.state.camera.mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame")
