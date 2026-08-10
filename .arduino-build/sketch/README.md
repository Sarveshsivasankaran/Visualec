#line 1 "D:\\Program files\\Visualec\\firmware\\visualec_esp32_s3\\README.md"
# ESP32-S3 firmware

Open `visualec_esp32_s3.ino` in Arduino IDE 2.x, select an ESP32-S3 board, install Espressif's `esp32` board package, and set `WIFI_SSID` and `WIFI_PASSWORD`. Relay pins and active-LOW behavior are configured together at the top of the sketch.

The three-relay prototype wiring is Relay 1 → GPIO 4, Relay 2 → GPIO 5, and Relay 3 → GPIO 6. The firmware, backend relay table, and physical IN1/IN2/IN3 wiring must use those same pins.

Flash with relay power disconnected. After boot, read the assigned IP at 115200 baud and test `GET /health` before connecting loads. The controller always initializes relays OFF and preserves an emergency-stop latch across restarts.

## Zone commands

The configurable `ZONE_RELAY_MAP` maps Zone 1–3 to Relay 1–3. The laptop remains responsible for computer-vision occupancy decisions and sends one of these commands when a stable zone state changes:

```text
POST /zone/1/active
POST /zone/1/inactive
GET  /zones
```

`active` drives the mapped relay ON and `inactive` drives it OFF. Existing `/relay/{id}/on` and `/relay/{id}/off` endpoints remain available and compatible with the Visualec backend.
