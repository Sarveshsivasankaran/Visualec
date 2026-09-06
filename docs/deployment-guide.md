# Deployment guide

## Host

Run Uvicorn on port 8000 and Vite on port 5173. Native backend execution is preferred on Windows for direct C270 access. Set a long random `EDGE_DEVICE_TOKEN`, explicit CORS origins, the camera index, and the verified artifact hash as `EDGE_EXPECTED_MODEL_SHA256` in `backend/.env`. Production rejects edge hello messages until the expected hash is configured. Do not install ML training requirements into the production backend environment.

## ESP32-S3 N16R8

Install ESP-IDF 5.3 or newer and open `firmware/visualec_edge_espidf` in an ESP-IDF shell. Configure Wi-Fi, `ws://<laptop-ip>:8000/ws/edge`, the shared token, active-low behavior, GPIOs, firmware version, and expected model hash.

Create and verify a release artifact first, then deploy:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\deploy_edge.ps1 `
  -Port COM5 `
  -ArtifactDir ml\artifacts\release
```

The script verifies real-frame provenance, SHA-256, size, dimensions, class list, quantization metadata, and quality gates before it invokes ESP-IDF. `sdkconfig.release` selects the custom Visualec-Pico artifact and prevents the managed bootstrap model from writing the same partition. The managed pedestrian model is for bring-up only.

## Production boundary

Use HTTPS/WSS through a private-network reverse proxy, authenticated operator roles, secrets outside source control, signed OTA images, database backups, and supervised processes. Do not expose the device WebSocket or rollback HTTP relay API to the public internet. Keep the Arduino image as a known rollback artifact, not a production inference path.
