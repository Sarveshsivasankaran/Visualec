import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import ManualOverride, RelayTest
from ..services.relay_service import RelayCommandError

router = APIRouter(prefix="/api/relays", tags=["relays"])


@router.get("")
def list_relays(request: Request) -> list[dict]:
    return request.app.state.runtime_state.snapshot()["relays"]


async def command(relay_id: int, desired: bool, request: Request, db: Session) -> dict:
    try:
        return await request.app.state.relay_service.set_state(db, relay_id, desired)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RelayCommandError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/{relay_id}/on")
async def on(relay_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    return await command(relay_id, True, request, db)


@router.post("/{relay_id}/off")
async def off(relay_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    return await command(relay_id, False, request, db)


@router.post("/{relay_id}/toggle")
async def toggle(relay_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    try:
        return await request.app.state.relay_service.toggle(db, relay_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{relay_id}/override")
async def override(relay_id: int, payload: ManualOverride, request: Request, db: Session = Depends(get_db)) -> dict:
    occupancy = request.app.state.occupancy_service
    duration = payload.duration_seconds
    if duration is None:
        duration = occupancy.deactivation_delay if payload.state else occupancy.activation_delay
    relay_service = request.app.state.relay_service
    runtime_state = request.app.state.runtime_state
    previous_mode = runtime_state.mode
    if not runtime_state.emergency:
        runtime_state.mode = "hybrid"
    relay_service.set_override(relay_id, payload.state, duration)
    try:
        result = await command(relay_id, payload.state, request, db)
    except Exception:
        runtime_state.manual_overrides.pop(relay_id, None)
        runtime_state.mode = previous_mode
        raise
    runtime_state.record_event(
        "override",
        f"Relay {relay_id} manually turned {'on' if payload.state else 'off'}; Hybrid mode active and Automatic resumes in {duration:g}s",
        source="dashboard",
        status="temporary",
        relay_id=relay_id,
        state="on" if payload.state else "off",
        duration_seconds=duration,
    )
    return {
        **result,
        "manual_override": True,
        "override_duration_seconds": duration,
        "mode": runtime_state.mode,
    }


@router.delete("/{relay_id}/override")
def cancel_override(relay_id: int, request: Request) -> dict:
    state = request.app.state.runtime_state
    state.manual_overrides.pop(relay_id, None)
    if state.mode == "hybrid" and not state.manual_overrides:
        state.mode = "automatic"
        state.record_event("mode", "Automatic control resumed", source="dashboard", status="automatic")
    return {"success": True, "mode": state.mode}


@router.post("/all-off")
async def all_off(request: Request, db: Session = Depends(get_db)) -> dict:
    return {"success": True, "results": await request.app.state.relay_service.all_off(db, "manual")}


@router.post("/test")
async def test(payload: RelayTest, request: Request, db: Session = Depends(get_db)) -> dict:
    await command(payload.relay_id, True, request, db)
    await asyncio.sleep(payload.duration_seconds)
    await command(payload.relay_id, False, request, db)
    return {"success": True, "relay_id": payload.relay_id}
