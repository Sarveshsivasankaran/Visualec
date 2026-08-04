import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import Base
from app.models import Relay
from app.services.relay_service import RelayCommandError, RelayService
from app.services.state import RuntimeState


class AcknowledgingTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"success": True, "device": "visualec-esp32-s3"})
        state = request.url.path.rsplit("/", 1)[-1]
        relay_id = int(request.url.path.split("/")[2])
        return httpx.Response(200, json={"success": True, "relay_id": relay_id, "state": state})


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
    service._client = httpx.AsyncClient(transport=AcknowledgingTransport())
    with Session(engine) as db:
        db.add(Relay(id=1, name="Lamp", gpio_pin=4))
        db.commit()
        first = await service.set_state(db, 1, True)
        second = await service.set_state(db, 1, True)
        assert first["duplicate"] is False
        assert second["duplicate"] is True
        state.emergency = True
        with pytest.raises(RelayCommandError):
            await service.set_state(db, 1, True)
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
