from fastapi import APIRouter, Request


router = APIRouter(prefix="/api/edge", tags=["edge"])


@router.get("/status")
def status(request: Request) -> dict:
    return request.app.state.runtime_state.snapshot()["edge"]


@router.post("/sync-config")
async def sync_config(request: Request) -> dict:
    edge = request.app.state.edge_service
    edge.bump_configuration_revision()
    await edge.send_current_config()
    return {"success": True, "configuration_revision": edge.state.edge.configuration_revision}
