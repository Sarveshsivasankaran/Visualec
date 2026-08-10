import json
import time

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import Base
from app.models import Relay
from app.services.relay_service import RelayCommandError, RelayService
from app.services.state import RuntimeState, ZoneRuntime


class AcknowledgingTransport(httpx.AsyncBaseTransport):
    def __init__(self, relay_states: dict[int, bool] | None = None, malformed_ack: bool = False) -> None:
        self.packets: list[dict] = []
        self.relay_states = relay_states or {1: False}
        self.malformed_ack = malformed_ack

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"success": True, "device": "visualec-esp32-s3"})
        if request.url.path == "/relays":
            return httpx.Response(200, json={
                "success": True,
                "relays": [
                    {"id": relay_id, "state": "on" if state else "off"}
                    for relay_id, state in sorted(self.relay_states.items())
                ],
            })
        assert request.url.path == "/control"
        packet = json.loads(request.content)
        self.packets.append(packet)
        self.relay_states[packet["relay_id"]] = packet["state"] == "on"
        if self.malformed_ack:
            return httpx.Response(200, text='{"success":true,"gpio_level":"HIGH,"state":"off"}')
        return httpx.Response(200, json={
            "success": True,
            "relay_id": packet["relay_id"],
            "state": packet["state"],
        })


class OfflineTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("offline", request=request)


@pytest.mark.asyncio
async def test_duplicate_prevention_and_emergency_stop():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    state = RuntimeState()
    state.relays[1] = False
    service = RelayService(Settings(), state)
    await service._client.aclose()
    transport = AcknowledgingTransport()
    service._client = httpx.AsyncClient(transport=transport)
    with Session(engine) as db:
        db.add(Relay(id=1, name="Lamp", gpio_pin=4))
        db.commit()
        first = await service.set_state(db, 1, True)
        second = await service.set_state(db, 1, True)
        assert first["duplicate"] is False
        assert second["duplicate"] is True
        assert len(transport.packets) == 1
        assert transport.packets[0]["relay_id"] == 1
        assert transport.packets[0]["state"] == "on"
        state.emergency = True
        with pytest.raises(RelayCommandError):
            await service.set_state(db, 1, True)
    await service.close()


@pytest.mark.asyncio
async def test_health_syncs_hardware_state_then_vacancy_forces_off():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    state = RuntimeState()
    state.relays[1] = False  # Stale backend state.
    state.zones[1] = ZoneRuntime(
        id=1,
        name="Zone 1",
        colour="#22d3ee",
        occupied=False,
        relay_ids=[1],
    )
    service = RelayService(Settings(), state)
    await service._client.aclose()
    transport = AcknowledgingTransport(relay_states={1: True})
    service._client = httpx.AsyncClient(transport=transport)

    assert await service.check_health() is True
    assert state.relays[1] is True
    with Session(engine) as db:
        db.add(Relay(id=1, name="Zone 1 load", gpio_pin=4, state=False))
        db.commit()
        await service.reconcile_automatic(db, 1.0, 10.0)

    assert transport.packets[-1]["state"] == "off"
    assert transport.relay_states[1] is False
    assert state.relays[1] is False
    await service.close()


@pytest.mark.asyncio
async def test_malformed_ack_uses_physical_relay_readback():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    state = RuntimeState()
    state.relays[1] = True
    service = RelayService(Settings(), state)
    await service._client.aclose()
    transport = AcknowledgingTransport(relay_states={1: True}, malformed_ack=True)
    service._client = httpx.AsyncClient(transport=transport)

    with Session(engine) as db:
        db.add(Relay(id=1, name="Zone 1 load", gpio_pin=4, state=True))
        db.commit()
        response = await service.set_state(db, 1, False, source="computer_vision")

    assert response["acknowledged"] is True
    assert response["acknowledged_by"] == "relay_readback"
    assert transport.relay_states[1] is False
    await service.close()


@pytest.mark.asyncio
async def test_automatic_occupancy_sends_json_packet_with_dashboard_delays():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    state = RuntimeState()
    state.esp32_connected = True
    state.relays[1] = False
    state.zones[1] = ZoneRuntime(
        id=1,
        name="Zone 1",
        colour="#22d3ee",
        occupied=True,
        people_count=1,
        relay_ids=[1],
    )
    service = RelayService(Settings(), state)
    await service._client.aclose()
    transport = AcknowledgingTransport()
    service._client = httpx.AsyncClient(transport=transport)

    with Session(engine) as db:
        db.add(Relay(id=1, name="Zone 1 load", gpio_pin=4))
        db.commit()
        await service.reconcile_automatic(db, 1.5, 12.0)
        state.zones[1].occupied = False
        state.zones[1].people_count = 0
        await service.reconcile_automatic(db, 1.5, 12.0)

    assert len(transport.packets) == 2
    packet = transport.packets[0]
    assert packet["event_type"] == "occupancy_control"
    assert packet["source"] == "computer_vision"
    assert packet["zone_id"] == 1
    assert packet["occupied"] is True
    assert packet["state"] == "on"
    assert packet["activation_delay_seconds"] == 1.5
    assert packet["deactivation_delay_seconds"] == 12.0
    off_packet = transport.packets[1]
    assert off_packet["event_type"] == "occupancy_control"
    assert off_packet["occupied"] is False
    assert off_packet["occupied_zone_ids"] == []
    assert off_packet["state"] == "off"
    assert off_packet["deactivation_delay_seconds"] == 12.0
    await service.close()


@pytest.mark.asyncio
async def test_expired_manual_override_returns_control_to_detection():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    state = RuntimeState()
    state.esp32_connected = True
    state.relays[1] = False
    state.zones[1] = ZoneRuntime(
        id=1,
        name="Zone 1",
        colour="#22d3ee",
        occupied=True,
        people_count=1,
        relay_ids=[1],
    )
    state.mode = "hybrid"
    state.manual_overrides[1] = (False, time.monotonic() - 1)
    service = RelayService(Settings(), state)
    await service._client.aclose()
    transport = AcknowledgingTransport()
    service._client = httpx.AsyncClient(transport=transport)

    with Session(engine) as db:
        db.add(Relay(id=1, name="Zone 1 load", gpio_pin=4, state=False))
        db.commit()
        await service.reconcile_automatic(db, 1.0, 10.0)

    assert 1 not in state.manual_overrides
    assert state.mode == "automatic"
    assert transport.packets[-1]["source"] == "computer_vision"
    assert transport.packets[-1]["state"] == "on"
    assert state.relays[1] is True
    await service.close()


@pytest.mark.asyncio
async def test_esp32_timeout_is_reported():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    state = RuntimeState()
    state.relays[1] = False
    service = RelayService(Settings(relay_retries=0), state)
    await service._client.aclose()
    service._client = httpx.AsyncClient(transport=OfflineTransport())
    with Session(engine) as db:
        db.add(Relay(id=1, name="Lamp", gpio_pin=4))
        db.commit()
        with pytest.raises(RelayCommandError, match="ESP32 command failed"):
            await service.set_state(db, 1, True)
    await service.close()
