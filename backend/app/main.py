from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import Base, SessionLocal, engine
from .routers import analytics, camera, detection, relays, settings as settings_router, system, zones
from .services.camera_service import CameraService
from .services.detection_service import DetectionService
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
    zone_service = ZoneService(state)
    occupancy_service = OccupancyService(settings, state)
    relay_service = RelayService(settings, state)
    energy_service = EnergyService(settings, state)
    websocket_manager = WebSocketManager()
    with SessionLocal() as db:
        zone_service.seed_defaults(db)
        zone_service.reload(db)
    runtime = VisualecRuntime(state, camera_service, detector, zone_service, occupancy_service, relay_service, energy_service, websocket_manager)
    app.state.settings = settings
    app.state.runtime_state = state
    app.state.camera = camera_service
    app.state.detector = detector
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
for router in (camera.router, detection.router, zones.router, relays.router, analytics.router, settings_router.router, system.router):
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
