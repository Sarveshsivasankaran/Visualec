import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import OccupancyEvent, RelayEvent

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def start_for(period: str) -> datetime:
    days = {"daily": 1, "weekly": 7, "monthly": 30}.get(period, 1)
    return datetime.now(timezone.utc) - timedelta(days=days)


@router.get("/summary")
def summary(request: Request, period: str = Query("daily", pattern="^(daily|weekly|monthly)$"), db: Session = Depends(get_db)) -> dict:
    return request.app.state.energy_service.summary(db, start_for(period))


@router.get("/occupancy")
def occupancy(period: str = Query("daily", pattern="^(daily|weekly|monthly)$"), db: Session = Depends(get_db)) -> list[dict]:
    events = db.scalars(select(OccupancyEvent).where(OccupancyEvent.timestamp >= start_for(period)).order_by(OccupancyEvent.timestamp)).all()
    return [{"timestamp": event.timestamp, "zone_id": event.zone_id, "occupied": event.new_state} for event in events]


@router.get("/energy")
def energy(request: Request, period: str = "daily", db: Session = Depends(get_db)) -> dict:
    return request.app.state.energy_service.summary(db, start_for(period))


@router.get("/events")
def events(limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(RelayEvent).order_by(RelayEvent.timestamp.desc()).limit(limit)).all()
    return [
        {"id": row.id, "timestamp": row.timestamp, "type": "relay", "relay_id": row.relay_id,
         "previous_state": row.previous_state, "new_state": row.new_state, "source": row.source,
         "acknowledged": row.acknowledged}
        for row in rows
    ]


@router.get("/export")
def export(db: Session = Depends(get_db)) -> StreamingResponse:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "relay_id", "previous_state", "new_state", "source", "acknowledged"])
    for event in db.scalars(select(RelayEvent).order_by(RelayEvent.timestamp)).all():
        writer.writerow([event.timestamp.isoformat(), event.relay_id, event.previous_state, event.new_state, event.source, event.acknowledged])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=visualec-events.csv"})
