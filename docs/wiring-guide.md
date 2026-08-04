# ESP32-S3 wiring guide

Default control pins are GPIO 4, 5, 6, and 7 for relays 1–4. Connect ESP32 ground to the relay module's logic ground and use the module's specified logic/power supply. Many boards are active-LOW; configure `RELAY_ACTIVE_LOW` before flashing.

Prototype procedure:

1. Keep all load power disconnected.
2. Flash firmware and confirm every output reports OFF.
3. Connect one relay input at a time and test with an LED or low-voltage bulb.
4. Verify the boot sequence and Wi-Fi loss do not energize a relay.
5. Label each relay and configure mappings in Zone Studio.

Do not connect mains wiring to a breadboard or exposed relay PCB. Any AC installation requires an appropriately rated enclosure, protection devices, isolation distances, grounding, and a qualified electrician.
