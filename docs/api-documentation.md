# API documentation

Interactive OpenAPI documentation is generated at `/docs` and the schema at `/openapi.json`.

| Category | Endpoints |
|---|---|
| Camera | `GET /api/camera/devices`, `GET /status`, `POST /start`, `POST /stop`, `POST /select`, `GET /frame`, `GET /stream` |
| Detection | `GET /api/detection/status`, `POST /start`, `POST /stop`, `PUT /settings`, `GET /latest` |
| Zones | `GET/POST /api/zones`, `PUT/DELETE /api/zones/{id}`, `POST /api/zones/reset-default` |
| Relays | `GET /api/relays`, `POST /{id}/on|off|toggle`, `POST /{id}/override`, `POST /all-off`, `POST /test` |
| Analytics | `GET /api/analytics/summary|occupancy|energy|events|export` |
| System | `GET /api/system/health|status|logs`, `POST /emergency-stop`, `POST /reset` |
| Settings | `GET/PUT /api/settings` |

Connect to `/ws` for `system_update` messages. The client should reconnect with capped exponential backoff. Relay HTTP failures return 503, missing IDs return 404, and invalid Pydantic payloads return 422.
