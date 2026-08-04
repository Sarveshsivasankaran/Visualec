# Testing guide

Run backend unit/API tests with `pytest -q` and compile the UI with `npm run build`.

Manual software checklist:

- Disconnect the webcam; confirm the UI reports it offline, no replacement frames appear, and automatic reconnection starts.
- Walk through each configured zone and check assignment uses the live bounding box bottom-center point.
- Hold occupancy beyond activation delay; confirm one ON event only.
- Clear a zone briefly, then longer than deactivation delay; confirm only the latter turns OFF.
- Apply an override, verify automatic state cannot replace it, cancel/expire it, and verify automation resumes.
- Activate emergency stop; confirm detection stops, all relays turn OFF, ON commands fail, and reset is explicit.
- Stop the backend; confirm frontend shows reconnecting, then restarts telemetry automatically.

Hardware checklist:

- Test `/health`, `/relays`, each ON/OFF/toggle command, invalid relay IDs, repeated `X-Command-ID`, all-off, and emergency latch.
- Disconnect Wi-Fi during a command and verify bounded backend failure plus visible offline state.
- Power-cycle the ESP32 ten times with low-voltage loads and verify no unintended activation.
- Disconnect the camera during an occupied state and verify the configured safety policy.
