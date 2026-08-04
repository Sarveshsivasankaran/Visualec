# ESP32-S3 firmware

Open `visualec_esp32_s3.ino` in Arduino IDE 2.x, select an ESP32-S3 board, install Espressif's `esp32` board package, and set `WIFI_SSID` and `WIFI_PASSWORD`. Relay pins and active-LOW behavior are configured together at the top of the sketch.

Flash with relay power disconnected. After boot, read the assigned IP at 115200 baud and test `GET /health` before connecting loads. The controller always initializes relays OFF and preserves an emergency-stop latch across restarts.
