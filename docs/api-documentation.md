# API documentation

Interactive OpenAPI documentation is generated at `/docs`; the schema is at `/openapi.json`.

| Category | Endpoints |
|---|---|
| Camera | `GET /api/camera/devices`, `GET /status`, `POST /start`, `POST /stop`, `POST /select`, `GET /frame`, `GET /stream` |
| Detection | `GET /api/detection/status`, `POST /start`, `POST /stop`, `PUT /settings`, `GET /latest` |
| Edge | `GET /api/edge/status`, `POST /api/edge/sync-config` |
| Zones | `GET/POST /api/zones`, `PUT/DELETE /api/zones/{id}`, `POST /api/zones/reset-default` |
| Relays | `GET /api/relays`, `POST /{id}/on|off|toggle`, `POST /{id}/override`, `POST /all-off`, `POST /test` |
| Analytics | `GET /api/analytics/summary|occupancy|energy|events|export` |
| System | `GET /api/system/health|status|logs`, `POST /emergency-stop`, `POST /reset` |
| Settings | `GET/PUT /api/settings` |

Browser clients connect to `/ws` for `system_update` state. The ESP connects to `/ws/edge?token=<EDGE_DEVICE_TOKEN>`. The first device message must be `hello`; configuration is revisioned, and stale revisions are ignored. Device acknowledgements are correlated by command ID and are returned to REST callers only after GPIO application.

The binary keyframe format is implemented and tested in `backend/app/services/edge_protocol.py`. JSON boxes use edge-input coordinates and are restored to the original camera coordinates using the recorded letterbox transform.
