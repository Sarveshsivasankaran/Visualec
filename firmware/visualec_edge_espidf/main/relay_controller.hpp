#pragma once

#include <cstdint>

#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

class RelayController {
public:
    static constexpr int kMaxRelays = 4;
    static constexpr int kMaxZones = 8;

    using ChangeCallback = void (*)(int relay_id, bool state, const char *reason);

    RelayController();
    void begin(ChangeCallback callback);
    void configure_delays(float activation_seconds, float deactivation_seconds, float stale_timeout_seconds);
    bool configure_relay(int relay_id, int gpio_pin, bool active_low);
    bool configure_zone(int zone_id, uint32_t relay_mask, bool enabled);
    void update_zone(int zone_id, bool occupied, int64_t now_us);
    void manual_override(int relay_id, bool state, float duration_seconds, int64_t now_us);
    void cancel_override(int relay_id);
    void set_emergency(bool active);
    void set_link_connected(bool connected, int64_t now_us);
    void note_occupancy_heartbeat(int64_t now_us);
    void tick(int64_t now_us);

    bool relay_state(int relay_id) const;
    int relay_gpio_level(int relay_id) const;
    const char *relay_mode(int relay_id) const;
    bool zone_state(int zone_id) const;
    bool emergency() const { return emergency_; }
    int configured_relays() const { return configured_relays_; }

private:
    struct Relay {
        bool configured = false;
        gpio_num_t pin = GPIO_NUM_NC;
        bool active_low = true;
        bool output = false;
        bool override_active = false;
        bool override_state = false;
        int64_t override_until_us = 0;
        const char *mode = "safe_off";
    };

    struct Zone {
        bool configured = false;
        bool enabled = true;
        bool raw = false;
        bool stable = false;
        int64_t raw_changed_at_us = 0;
        uint32_t relay_mask = 0;
    };

    void write_relay_locked(int index, bool state, const char *reason);
    bool stale_locked(int64_t now_us) const;

    Relay relays_[kMaxRelays];
    Zone zones_[kMaxZones];
    int configured_relays_ = 0;
    float activation_seconds_ = 1.0f;
    float deactivation_seconds_ = 10.0f;
    float stale_timeout_seconds_ = 30.0f;
    bool emergency_ = false;
    bool link_connected_ = false;
    int64_t disconnected_at_us_ = 0;
    int64_t last_heartbeat_us_ = 0;
    ChangeCallback callback_ = nullptr;
    SemaphoreHandle_t mutex_ = nullptr;
};
