from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Relay, RelayEvent
from .state import RuntimeState


def energy_kwh(power_watts: float, duration_seconds: float) -> float:
    return power_watts * duration_seconds / 3_600_000


class EnergyService:
    def __init__(self, settings: Settings, state: RuntimeState) -> None:
        self.settings = settings
        self.state = state

    def current_power(self) -> float:
        return round(sum(self.state.relay_wattages.get(relay_id, 0) for relay_id, on in self.state.relays.items() if on), 2)

    def summary(self, db: Session, since: datetime | None = None) -> dict:
        now = datetime.now(timezone.utc)
        since = since or now - timedelta(days=1)
        relays = db.scalars(select(Relay)).all()
        events = db.scalars(select(RelayEvent).where(RelayEvent.timestamp >= since).order_by(RelayEvent.timestamp)).all()
        wattages = {relay.id: relay.rated_wattage for relay in relays}
        initial = {relay.id: False for relay in relays}
        last_at = {relay.id: since for relay in relays}
        runtime = {relay.id: 0.0 for relay in relays}
        for event in events:
            event_time = event.timestamp if event.timestamp.tzinfo else event.timestamp.replace(tzinfo=timezone.utc)
            relay_id = event.relay_id
            if initial.get(relay_id):
                runtime[relay_id] += max(0, (event_time - last_at[relay_id]).total_seconds())
            initial[relay_id] = event.new_state
            last_at[relay_id] = event_time
        for relay_id, is_on in initial.items():
            if is_on:
                runtime[relay_id] += max(0, (now - last_at[relay_id]).total_seconds())
        actual = sum(energy_kwh(wattages.get(relay_id, 0), seconds) for relay_id, seconds in runtime.items())
        duration = max(0, (now - since).total_seconds())
        baseline = energy_kwh(sum(wattages.values()), duration)
        saved = max(0, baseline - actual)
        return {
            "period_start": since.isoformat(),
            "current_power_watts": self.current_power(),
            "actual_energy_kwh": round(actual, 6),
            "baseline_energy_kwh": round(baseline, 6),
            "energy_saved_kwh": round(saved, 6),
            "cost_saved": round(saved * self.settings.energy_tariff_per_kwh, 2),
            "relay_activations": sum(1 for event in events if event.new_state),
            "zone_usage": [
                {"relay_id": relay.id, "name": relay.name, "runtime_seconds": round(runtime[relay.id], 1), "energy_kwh": round(energy_kwh(relay.rated_wattage, runtime[relay.id]), 6)}
                for relay in relays
            ],
        }
