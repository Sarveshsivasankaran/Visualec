# Visualec ESP32-S3 edge firmware

This ESP-IDF 5.3+ application is the production edge path for an ESP32-S3 N16R8. It connects outbound to the authenticated FastAPI `/ws/edge` endpoint, receives CRC-protected RGB565 keyframes, runs ESP-DL person detection, returns frame-linked boxes, and owns occupancy delays plus relay safety.

The existing `firmware/visualec_esp32_s3` Arduino sketch remains the relay-only rollback firmware.

## Build and flash

```powershell
cd firmware\visualec_edge_espidf
idf.py set-target esp32s3
idf.py menuconfig
idf.py build
idf.py -p COM5 flash monitor
```

Under **Visualec edge configuration**, set Wi-Fi credentials, the laptop WebSocket URL, and the same device token configured as `EDGE_DEVICE_TOKEN` in `backend/.env`.

The managed Espressif pedestrian Pico model is available for bring-up. The release configuration replaces it with a verified Visualec-Pico 160×288 `.espdl`. Use `scripts\flash_edge_candidate.ps1` for the first laboratory flash after real-data and host-quality gates pass. Use `scripts\deploy_edge.ps1` only after recorded physical ESP predictions satisfy the release gate. No laptop detector or generated-frame fallback exists.

## Safety and timing

- GPIO outputs initialize OFF before networking starts.
- Emergency stop is persisted in NVS and remains latched until explicit reset.
- Priority is emergency, stale-input safe-off, manual override, then automatic occupancy.
- A disconnected link cannot create a new ON decision; automatic outputs go OFF after the camera-loss timeout.
- Manual OFF expires after the activation delay and manual ON expires after the deactivation delay.
- Occupancy with a stale configuration revision is rejected and does not refresh the safety heartbeat.
- Relay acknowledgements include requested/effective state, physical GPIO level, mode, command ID, and revision after GPIO application.

Use low-voltage loads for validation. Mains wiring requires an enclosed, correctly rated relay/contactor assembly installed by a qualified electrician.
