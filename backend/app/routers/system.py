from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health")
def health(request: Request, db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    snapshot = request.app.state.runtime_state.snapshot()
    return {
        "status": "degraded" if snapshot["emergency"] or not snapshot["camera"]["connected"] or not snapshot["esp32"]["connected"] or snapshot["detection"]["error"] else "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": "connected",
        "camera": snapshot["camera"]["health"],
        "esp32": "connected" if snapshot["esp32"]["connected"] else "offline",
    }


@router.get("/status")
def status(request: Request, db: Session = Depends(get_db)) -> dict:
    payload = request.app.state.runtime_state.snapshot()
    payload["energy"] = request.app.state.energy_service.summary(db)
    return payload


@router.get("/logs")
def logs(request: Request) -> list[dict]:
    return request.app.state.runtime_state.events[:15]


@router.post("/emergency-stop")
async def emergency_stop(request: Request, db: Session = Depends(get_db)) -> dict:
    state = request.app.state.runtime_state
    state.emergency = True
    state.mode = "manual"
    request.app.state.detector.stop()
    state.alert("critical", "Emergency stop activated")
    results = await request.app.state.relay_service.all_off(db, "emergency")
    return {"success": all(item.get("success") for item in results), "emergency": True, "results": results}


@router.post("/reset")
def reset(request: Request) -> dict:
    state = request.app.state.runtime_state
    state.emergency = False
    state.mode = "automatic"
    request.app.state.detector.start()
    state.alert("info", "System reset completed")
    return {"success": True, "emergency": False, "mode": state.mode}
