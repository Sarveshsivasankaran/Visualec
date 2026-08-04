import asyncio
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Relay, RelayEvent
from .state import RuntimeState


class RelayCommandError(RuntimeError):
    pass


class RelayService:
    def __init__(self, settings: Settings, state: RuntimeState) -> None:
        self.settings = settings
        self.state = state
        self._client = httpx.AsyncClient(timeout=settings.esp32_timeout_seconds)
        self._command_lock = asyncio.Lock()

    async def close(self) -> None:
        await self._client.aclose()

    async def check_health(self) -> bool:
        previous = self.state.esp32_connected
        try:
            response = await self._client.get(f"{self.settings.esp32_base_url}/health")
            response.raise_for_status()
            payload = response.json()
            connected = bool(payload.get("success"))
        except (httpx.HTTPError, ValueError):
            connected = False
        self.state.esp32_connected = connected
        if connected != previous:
            self.state.alert("info" if connected else "error", "ESP32 connected" if connected else "ESP32 disconnected")
        return connected

    async def set_state(self, db: Session, relay_id: int, desired: bool, source: str = "manual", force: bool = False) -> dict:
        relay = db.get(Relay, relay_id)
        if relay is None:
            raise KeyError(f"Relay {relay_id} does not exist")
        if self.state.emergency and desired and not force:
            raise RelayCommandError("Emergency stop is active")
        with self.state.lock:
            current = self.state.relays.get(relay_id, relay.state)
        if current == desired and self.state.esp32_connected and not force:
            return {"success": True, "relay_id": relay_id, "state": "on" if desired else "off", "duplicate": True, "acknowledged": True}
        started = time.perf_counter()
        acknowledged = False
        response: dict = {}
        async with self._command_lock:
            endpoint = f"{self.settings.esp32_base_url}/relay/{relay_id}/{'on' if desired else 'off'}"
            command_id = f"{relay_id}-{int(time.time()*1000)}"
            error: Exception | None = None
            for attempt in range(self.settings.relay_retries + 1):
                try:
                    result = await self._client.post(endpoint, headers={"X-Command-ID": command_id})
                    result.raise_for_status()
                    response = result.json()
                    acknowledged = bool(response.get("success")) and response.get("state") == ("on" if desired else "off")
                    if acknowledged:
                        break
                    error = RelayCommandError("Device response did not confirm the requested state")
                except (httpx.HTTPError, ValueError) as exc:
                    error = exc
                if attempt < self.settings.relay_retries:
                    await asyncio.sleep(.15 * (attempt + 1))
            if not acknowledged:
                self.state.esp32_connected = False
                raise RelayCommandError(f"ESP32 command failed: {error}")
        elapsed = (time.perf_counter() - started) * 1000
        relay.state = desired
        relay.last_updated = datetime.now(timezone.utc)
        db.add(RelayEvent(
            relay_id=relay_id, previous_state=current, new_state=desired, source=source,
            acknowledged=acknowledged, response_time_ms=elapsed,
        ))
        db.commit()
        with self.state.lock:
            self.state.relays[relay_id] = desired
            self.state.esp32_connected = True
        self.state.record_event(
            "relay",
            f"{relay.name} turned {'on' if desired else 'off'}",
            source=source,
            status="acknowledged",
            relay_id=relay_id,
            state="on" if desired else "off",
            response_time_ms=round(elapsed, 1),
        )
        return {
            "success": True, "relay_id": relay_id, "state": "on" if desired else "off",
            "duplicate": False, "acknowledged": acknowledged, "response_time_ms": round(elapsed, 1), **response,
        }

    async def toggle(self, db: Session, relay_id: int, source: str = "manual") -> dict:
        return await self.set_state(db, relay_id, not self.state.relays.get(relay_id, False), source)

    async def all_off(self, db: Session, source: str = "safety") -> list[dict]:
        results = []
        for relay_id in sorted(self.state.relays):
            try:
                results.append(await self.set_state(db, relay_id, False, source, force=self.state.emergency))
            except RelayCommandError as exc:
                results.append({"success": False, "relay_id": relay_id, "state": "unknown", "acknowledged": False, "error": str(exc)})
        return results

    def set_override(self, relay_id: int, state: bool, duration_seconds: int) -> None:
        self.state.manual_overrides[relay_id] = (state, time.monotonic() + duration_seconds)

    async def reconcile_automatic(self, db: Session) -> None:
        if self.state.emergency or self.state.mode == "manual" or not self.state.esp32_connected:
            return
        now = time.monotonic()
        expired = [relay_id for relay_id, (_state, until) in self.state.manual_overrides.items() if until <= now]
        for relay_id in expired:
            self.state.manual_overrides.pop(relay_id, None)
        desired: dict[int, bool] = {}
        for zone in self.state.zones.values():
            if zone.auto_control_enabled:
                for relay_id in zone.relay_ids:
                    desired[relay_id] = desired.get(relay_id, False) or zone.occupied
        for relay_id, relay_state in desired.items():
            override = self.state.manual_overrides.get(relay_id)
            await self.set_state(db, relay_id, override[0] if override else relay_state, "override" if override else "automatic")
