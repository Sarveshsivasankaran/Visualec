from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Zone, ZoneRelayMapping
from ..schemas import ZoneCreate, ZoneUpdate

router = APIRouter(prefix="/api/zones", tags=["zones"])


def query_zones(db: Session) -> list[Zone]:
    return list(db.scalars(select(Zone).options(selectinload(Zone.mappings)).order_by(Zone.id)).all())


@router.get("")
def list_zones(db: Session = Depends(get_db)) -> list[dict]:
    from ..services.zone_service import ZoneService
    return [ZoneService.serialize(zone) for zone in query_zones(db)]


@router.post("", status_code=201)
def create(payload: ZoneCreate, request: Request, db: Session = Depends(get_db)) -> dict:
    zone = Zone(**payload.model_dump(exclude={"relay_ids", "auto_control_enabled"}, mode="json"))
    db.add(zone)
    db.flush()
    for relay_id in payload.relay_ids:
        db.add(ZoneRelayMapping(zone_id=zone.id, relay_id=relay_id, auto_control_enabled=payload.auto_control_enabled))
    db.commit()
    request.app.state.zone_service.reload(db)
    return {"id": zone.id, **payload.model_dump(mode="json")}


@router.put("/{zone_id}")
def update(zone_id: int, payload: ZoneUpdate, request: Request, db: Session = Depends(get_db)) -> dict:
    zone = db.get(Zone, zone_id)
    if zone is None:
        raise HTTPException(404, "Zone not found")
    data = payload.model_dump(exclude={"relay_ids", "auto_control_enabled"}, mode="json")
    for key, value in data.items():
        setattr(zone, key, value)
    db.execute(delete(ZoneRelayMapping).where(ZoneRelayMapping.zone_id == zone_id))
    for relay_id in payload.relay_ids:
        db.add(ZoneRelayMapping(zone_id=zone_id, relay_id=relay_id, auto_control_enabled=payload.auto_control_enabled))
    db.commit()
    request.app.state.zone_service.reload(db)
    return {"id": zone_id, **payload.model_dump(mode="json")}


@router.delete("/{zone_id}", status_code=204)
def remove(zone_id: int, request: Request, db: Session = Depends(get_db)) -> Response:
    zone = db.get(Zone, zone_id)
    if zone is None:
        raise HTTPException(404, "Zone not found")
    db.delete(zone)
    db.commit()
    request.app.state.zone_service.reload(db)
    return Response(status_code=204)


@router.post("/reset-default")
def reset(request: Request, db: Session = Depends(get_db)) -> list[dict]:
    db.execute(delete(ZoneRelayMapping))
    db.execute(delete(Zone))
    db.commit()
    request.app.state.zone_service.seed_defaults(db)
    request.app.state.zone_service.reload(db)
    return list_zones(db)
