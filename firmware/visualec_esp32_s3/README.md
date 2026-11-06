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

## Backend JSON control packets

The preferred backend command is `POST /control` with `Content-Type: application/json`. The backend sends this only after the dashboard-configured occupancy delay has elapsed, so the ESP32 applies the GPIO output immediately and does not add a second delay.

```json
{
  "command_id": "relay-1-1723123456789",
  "event_type": "occupancy_control",
  "source": "computer_vision",
  "zone_id": 1,
  "relay_id": 1,
  "state": "on",
  "activation_delay_seconds": 1.0,
  "deactivation_delay_seconds": 10.0
}
```

The response acknowledges the logical relay state, GPIO pin, and electrical output level. For an active-LOW module, `state: "on"` correctly produces `gpio_level: "LOW"`.
