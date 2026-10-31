from contextlib import asynccontextmanager

import hmac

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import Base, SessionLocal, engine
from .routers import analytics, camera, detection, edge, relays, settings as settings_router, system, zones
from .services.camera_service import CameraService
from .services.detection_service import DetectionService
from .services.edge_inference_service import EdgeInferenceService
from .services.energy_service import EnergyService
from .services.occupancy_service import OccupancyService
from .services.relay_service import RelayService
from .services.runtime import VisualecRuntime
from .services.state import RuntimeState
from .services.websocket_manager import WebSocketManager
from .services.zone_service import ZoneService
from .utils.logging import configure_logging

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    Base.metadata.create_all(engine)
    state = RuntimeState()
    state.mode = "automatic"
    camera_service = CameraService(settings, state)
    detector = DetectionService(settings, state)
    edge_service = EdgeInferenceService(settings, state)
    zone_service = ZoneService(state)
    occupancy_service = OccupancyService(settings, state)
    relay_service = RelayService(settings, state, edge_service=edge_service)
    energy_service = EnergyService(settings, state)
    websocket_manager = WebSocketManager()
    with SessionLocal() as db:
        zone_service.seed_defaults(db)
        zone_service.reload(db)
    runtime = VisualecRuntime(state, camera_service, detector, edge_service, zone_service, occupancy_service, relay_service, energy_service, websocket_manager)
    app.state.settings = settings
    app.state.runtime_state = state
    app.state.camera = camera_service
    app.state.detector = detector
    app.state.edge_service = edge_service
    app.state.zone_service = zone_service
    app.state.occupancy_service = occupancy_service
    app.state.relay_service = relay_service
    app.state.energy_service = energy_service
    app.state.websocket_manager = websocket_manager
    app.state.runtime = runtime
    state.record_event("system", "Visualec real-time services started", source="backend", status="online")
    if settings.auto_start_camera:
        camera_service.start()
    runtime.start()
    yield
    await runtime.stop()
    camera_service.stop()
    await relay_service.close()


settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
for router in (camera.router, detection.router, edge.router, zones.router, relays.router, analytics.router, settings_router.router, system.router):
    app.include_router(router)


@app.get("/")
def root() -> dict:
    return {"name": "Visualec API", "docs": "/docs", "health": "/api/system/health"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    manager: WebSocketManager = websocket.app.state.websocket_manager
    await manager.connect(websocket)
    try:
        await websocket.send_json(websocket.app.state.runtime_state.snapshot())
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await manager.disconnect(websocket)


@app.websocket("/ws/edge")
async def edge_websocket_endpoint(websocket: WebSocket) -> None:
    configured = websocket.app.state.settings.edge_device_token
    supplied = websocket.query_params.get("token") or websocket.headers.get("x-device-token", "")
    await websocket.accept()
    try:
        import socket
        transport = websocket.scope.get("transport")
        if transport is not None:
            raw_socket = transport.get_extra_info("socket")
            if raw_socket is not None:
                raw_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass
    if not configured or not hmac.compare_digest(configured, supplied):
        await websocket.close(code=1008, reason="invalid device token")
        return
    service: EdgeInferenceService = websocket.app.state.edge_service
    await service.connect(websocket)
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            text = message.get("text")
            if text is not None:
                await service.handle_text(text)
    except WebSocketDisconnect:
        pass
    finally:
        await service.disconnect(websocket)
