# ESP32-S3 wiring guide

Default control pins are GPIO 4, 5, 6, and 7 for relays 1–4. Connect ESP32 ground to the relay module logic ground and use the module specified logic/power supply. Many boards are active-LOW; configure the active-low setting before flashing.

Prototype procedure:

1. Keep all load power disconnected.
2. Flash `firmware/visualec_edge_espidf` and confirm every output reports OFF before the WebSocket connects.
3. Connect one relay input at a time and test with an LED or low-voltage bulb.
4. Verify boot, model failure, backend loss, stale occupancy, and Wi-Fi loss do not energize a relay.
5. Label each relay and configure mappings in Zone Studio; confirm the matching revision is acknowledged by the device.

Do not connect mains wiring to a breadboard or exposed relay PCB. Any AC installation requires an appropriately rated enclosure, protection devices, isolation distances, grounding, and a qualified electrician.
