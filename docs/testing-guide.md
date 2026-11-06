# Testing guide

## Host gates

```powershell
cd backend
pytest -q
cd ..\frontend
npm run build
```

Tests cover RGB565 preprocessing, VEC1 serialization/CRC, coordinate restoration, late-result rejection, temporal tracking, polygon assignment, configuration revision handling, and the 15-event live-state limit. Disconnect the ESP and confirm the dashboard reports edge inference unavailable without local or fabricated detections.

## Model gates

Use held-out sessions recorded separately from training and calibration. Compare YOLOv8n teacher, floating student, quantized host graph, and physical ESP output. The release gate requires at least 90% teacher person recall and no more than a three-point mAP50 loss from floating student to INT8. Every evaluated frame must trace to a physical C270 session manifest.

## Physical hardware acceptance

Run `scripts/benchmark_edge.py` while the physical C270, ESP32-S3 N16R8, and low-voltage relay loads are connected. Save raw WebSocket/device packets with the benchmark report.

| Gate | Requirement |
|---|---:|
| Camera tracking and zone output | at least 24 Hz |
| Edge inference during high motion | at least 7 FPS |
| ESP preprocessing + inference median | at most 140 ms |
| Detection round trip p95 | at most 200 ms, no backlog |
| Relay transition after delay expires | at most 300 ms |
| Occupied-room soak | no false OFF in 60 minutes |
| Vacancy | OFF by deactivation delay + 300 ms |

Also verify manual OFF and ON yield back to automatic with the specified activation/deactivation timing. Exercise emergency, Wi-Fi loss, backend loss, camera heartbeat loss, corrupt frames, stale results, reboot, model-hash mismatch, configuration revision mismatch, and relay active-level polarity. Hardware results remain “not measured” until this physical procedure produces evidence; do not substitute estimates or simulation.
