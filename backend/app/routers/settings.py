from fastapi import APIRouter, Request

from ..schemas import SystemSettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings(request: Request) -> dict:
    settings = request.app.state.settings
    occupancy = request.app.state.occupancy_service
    return {
        "camera_index": settings.camera_index,
        "camera_width": settings.camera_width,
        "camera_height": settings.camera_height,
        "detection_model": settings.detection_model,
        "detection_confidence": request.app.state.detector.confidence,
        "inference_interval_ms": request.app.state.detector.interval_ms,
        "activation_delay_seconds": occupancy.activation_delay,
        "deactivation_delay_seconds": occupancy.deactivation_delay,
        "esp32_base_url": settings.esp32_base_url,
        "energy_tariff_per_kwh": settings.energy_tariff_per_kwh,
        "mode": request.app.state.runtime_state.mode,
    }


@router.put("")
def update(payload: SystemSettingsUpdate, request: Request) -> dict:
    values = payload.model_dump(exclude_none=True)
    state = request.app.state.runtime_state
    if "mode" in values:
        state.mode = values["mode"]
    if "activation_delay_seconds" in values:
        request.app.state.occupancy_service.activation_delay = values["activation_delay_seconds"]
    if "deactivation_delay_seconds" in values:
        request.app.state.occupancy_service.deactivation_delay = values["deactivation_delay_seconds"]
    if "energy_tariff_per_kwh" in values:
        request.app.state.energy_service.settings.energy_tariff_per_kwh = values["energy_tariff_per_kwh"]
    if "esp32_base_url" in values:
        request.app.state.relay_service.settings.esp32_base_url = values["esp32_base_url"].rstrip("/")
        request.app.state.runtime_state.esp32_connected = False
    return {"success": True, **values}
