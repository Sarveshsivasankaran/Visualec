import asyncio
import time
from datetime import datetime, timezone
from typing import Any

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

    async def _read_device_relay_states(self) -> dict[int, bool]:
        response = await self._client.get(f"{self.settings.esp32_base_url}/relays")
        response.raise_for_status()
        payload = response.json()
        relays = payload.get("relays")
        if not payload.get("success") or not isinstance(relays, list):
            raise RelayCommandError("Device relay-state response is invalid")
        states: dict[int, bool] = {}
        for relay in relays:
            if not isinstance(relay, dict):
                continue
            relay_id = relay.get("id")
            relay_state = relay.get("state")
            if isinstance(relay_id, int) and relay_state in ("on", "off"):
                states[relay_id] = relay_state == "on"
        if not states:
            raise RelayCommandError("Device did not report any relay states")
        return states

    async def check_health(self) -> bool:
        previous = self.state.esp32_connected
        try:
            response = await self._client.get(f"{self.settings.esp32_base_url}/health")
            response.raise_for_status()
            payload = response.json()
            connected = bool(payload.get("success"))
            if connected:
                device_states = await self._read_device_relay_states()
                with self.state.lock:
                    self.state.relays.update(device_states)
        except (httpx.HTTPError, ValueError, RelayCommandError):
            connected = False
        self.state.esp32_connected = connected
        if connected != previous:
            self.state.alert("info" if connected else "error", "ESP32 connected" if connected else "ESP32 disconnected")
        return connected

    async def set_state(
        self,
        db: Session,
        relay_id: int,
        desired: bool,
        source: str = "manual",
        force: bool = False,
        packet_context: dict[str, Any] | None = None,
    ) -> dict:
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
            endpoint = f"{self.settings.esp32_base_url}/control"
            command_id = f"relay-{relay_id}-{time.time_ns()}"
            packet: dict[str, Any] = {
                "command_id": command_id,
                "event_type": "relay_control",
                "source": source,
                "relay_id": relay_id,
                "state": "on" if desired else "off",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if packet_context:
                packet.update(packet_context)
            error: Exception | None = None
            for attempt in range(self.settings.relay_retries + 1):
                try:
                    result = await self._client.post(
                        endpoint,
                        headers={"X-Command-ID": command_id},
                        json=packet,
                    )
                    result.raise_for_status()
                    try:
                        response = result.json()
                        acknowledged = bool(response.get("success")) and response.get("state") == ("on" if desired else "off")
                    except ValueError:
                        # A physical readback is authoritative even if an older firmware
                        # returns a malformed command acknowledgement.
                        device_states = await self._read_device_relay_states()
                        acknowledged = device_states.get(relay_id) == desired
                        response = {
                            "success": acknowledged,
                            "relay_id": relay_id,
                            "state": "on" if desired else "off",
                            "acknowledged_by": "relay_readback",
                        }
                    if acknowledged:
                        break
                    error = RelayCommandError("Device response did not confirm the requested state")
                except (httpx.HTTPError, ValueError, RelayCommandError) as exc:
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
            command_id=command_id,
            packet_type=packet["event_type"],
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

    def set_override(self, relay_id: int, state: bool, duration_seconds: float) -> None:
        self.state.manual_overrides[relay_id] = (state, time.monotonic() + duration_seconds)

    async def reconcile_automatic(
        self,
        db: Session,
        activation_delay_seconds: float | None = None,
        deactivation_delay_seconds: float | None = None,
    ) -> None:
        now = time.monotonic()
        expired = [relay_id for relay_id, (_state, until) in self.state.manual_overrides.items() if until <= now]
        for relay_id in expired:
            self.state.manual_overrides.pop(relay_id, None)
        if expired and self.state.mode == "hybrid" and not self.state.manual_overrides:
            self.state.mode = "automatic"
            self.state.record_event(
                "mode",
                "Temporary manual control ended; Automatic control resumed",
                source="runtime",
                status="automatic",
            )
        if self.state.emergency or self.state.mode == "manual" or not self.state.esp32_connected:
            return
        desired: dict[int, bool] = {}
        for zone in self.state.zones.values():
            if zone.auto_control_enabled:
                for relay_id in zone.relay_ids:
                    desired[relay_id] = desired.get(relay_id, False) or zone.occupied
        for relay_id, relay_state in desired.items():
            override = self.state.manual_overrides.get(relay_id)
            zone_ids = sorted(
                zone.id
                for zone in self.state.zones.values()
                if zone.auto_control_enabled and relay_id in zone.relay_ids
            )
            occupied_zone_ids = sorted(
                zone.id
                for zone in self.state.zones.values()
                if zone.auto_control_enabled and zone.occupied and relay_id in zone.relay_ids
            )
            packet_context: dict[str, Any] = {
                "event_type": "occupancy_control",
                "zone_ids": zone_ids,
                "occupied_zone_ids": occupied_zone_ids,
                "occupied": bool(occupied_zone_ids),
            }
            if len(zone_ids) == 1:
                packet_context["zone_id"] = zone_ids[0]
            if activation_delay_seconds is not None:
                packet_context["activation_delay_seconds"] = activation_delay_seconds
            if deactivation_delay_seconds is not None:
                packet_context["deactivation_delay_seconds"] = deactivation_delay_seconds
            await self.set_state(
                db,
                relay_id,
                override[0] if override else relay_state,
                "override" if override else "computer_vision",
                packet_context=packet_context,
            )
