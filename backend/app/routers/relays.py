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
    request.app.state.relay_service.set_override(relay_id, payload.state, payload.duration_seconds)
    return await command(relay_id, payload.state, request, db)


@router.delete("/{relay_id}/override")
def cancel_override(relay_id: int, request: Request) -> dict:
    request.app.state.runtime_state.manual_overrides.pop(relay_id, None)
    return {"success": True}


@router.post("/all-off")
async def all_off(request: Request, db: Session = Depends(get_db)) -> dict:
    return {"success": True, "results": await request.app.state.relay_service.all_off(db, "manual")}


@router.post("/test")
async def test(payload: RelayTest, request: Request, db: Session = Depends(get_db)) -> dict:
    await command(payload.relay_id, True, request, db)
    await asyncio.sleep(payload.duration_seconds)
    await command(payload.relay_id, False, request, db)
    return {"success": True, "relay_id": payload.relay_id}
