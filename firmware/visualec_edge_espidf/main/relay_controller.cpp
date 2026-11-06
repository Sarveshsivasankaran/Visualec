#include "relay_controller.hpp"

#include <algorithm>

RelayController::RelayController() = default;

void RelayController::begin(ChangeCallback callback)
{
    callback_ = callback;
    mutex_ = xSemaphoreCreateMutex();
}

void RelayController::configure_delays(float activation_seconds, float deactivation_seconds, float stale_timeout_seconds)
{
    xSemaphoreTake(mutex_, portMAX_DELAY);
    activation_seconds_ = std::max(0.0f, activation_seconds);
    deactivation_seconds_ = std::max(0.0f, deactivation_seconds);
    stale_timeout_seconds_ = std::max(1.0f, stale_timeout_seconds);
    xSemaphoreGive(mutex_);
}

bool RelayController::configure_relay(int relay_id, int gpio_pin, bool active_low)
{
    if (relay_id < 1 || relay_id > kMaxRelays || !GPIO_IS_VALID_OUTPUT_GPIO(gpio_pin)) {
        return false;
    }
    xSemaphoreTake(mutex_, portMAX_DELAY);
    Relay &relay = relays_[relay_id - 1];
    if (relay.configured && relay.pin == gpio_pin && relay.active_low == active_low) {
        xSemaphoreGive(mutex_);
        return true;
    }
    if (relay.configured) {
        gpio_set_level(relay.pin, relay.active_low ? 1 : 0);
    }
    if (!relay.configured) {
        configured_relays_++;
    }
    relay.configured = true;
    relay.pin = static_cast<gpio_num_t>(gpio_pin);
    relay.active_low = active_low;
    gpio_set_level(relay.pin, active_low ? 1 : 0);
    gpio_reset_pin(relay.pin);
    gpio_set_direction(relay.pin, GPIO_MODE_OUTPUT);
    gpio_set_level(relay.pin, active_low ? 1 : 0);
    relay.output = false;
    xSemaphoreGive(mutex_);
    return true;
}

bool RelayController::configure_zone(int zone_id, uint32_t relay_mask, bool enabled)
{
    if (zone_id < 1 || zone_id > kMaxZones) {
        return false;
    }
    xSemaphoreTake(mutex_, portMAX_DELAY);
    Zone &zone = zones_[zone_id - 1];
    zone.configured = true;
    zone.enabled = enabled;
    zone.relay_mask = relay_mask;
    xSemaphoreGive(mutex_);
    return true;
}

void RelayController::update_zone(int zone_id, bool occupied, int64_t now_us)
{
    if (zone_id < 1 || zone_id > kMaxZones) return;
    xSemaphoreTake(mutex_, portMAX_DELAY);
    Zone &zone = zones_[zone_id - 1];
    if (zone.configured && zone.raw != occupied) {
        zone.raw = occupied;
        zone.raw_changed_at_us = now_us;
    }
    last_heartbeat_us_ = now_us;
    xSemaphoreGive(mutex_);
}

void RelayController::manual_override(int relay_id, bool state, float duration_seconds, int64_t now_us)
{
    if (relay_id < 1 || relay_id > kMaxRelays) return;
    xSemaphoreTake(mutex_, portMAX_DELAY);
    Relay &relay = relays_[relay_id - 1];
    relay.override_active = true;
    relay.override_state = state;
    relay.override_until_us = now_us + static_cast<int64_t>(std::max(0.0f, duration_seconds) * 1'000'000.0f);
    xSemaphoreGive(mutex_);
    tick(now_us);
}

void RelayController::cancel_override(int relay_id)
{
    if (relay_id < 1 || relay_id > kMaxRelays) return;
    xSemaphoreTake(mutex_, portMAX_DELAY);
    relays_[relay_id - 1].override_active = false;
    xSemaphoreGive(mutex_);
}

void RelayController::set_emergency(bool active)
{
    xSemaphoreTake(mutex_, portMAX_DELAY);
    emergency_ = active;
    xSemaphoreGive(mutex_);
}

void RelayController::set_link_connected(bool connected, int64_t now_us)
{
    xSemaphoreTake(mutex_, portMAX_DELAY);
    if (link_connected_ && !connected) {
        disconnected_at_us_ = now_us;
    }
    link_connected_ = connected;
    if (connected) {
        disconnected_at_us_ = 0;
    }
    xSemaphoreGive(mutex_);
}

void RelayController::note_occupancy_heartbeat(int64_t now_us)
{
    xSemaphoreTake(mutex_, portMAX_DELAY);
    last_heartbeat_us_ = now_us;
    xSemaphoreGive(mutex_);
}

bool RelayController::stale_locked(int64_t now_us) const
{
    const int64_t timeout_us = static_cast<int64_t>(stale_timeout_seconds_ * 1'000'000.0f);
    if (!link_connected_) {
        return disconnected_at_us_ > 0 && now_us - disconnected_at_us_ >= timeout_us;
    }
    return last_heartbeat_us_ > 0 && now_us - last_heartbeat_us_ >= timeout_us;
}

void RelayController::write_relay_locked(int index, bool state, const char *reason)
{
    Relay &relay = relays_[index];
    if (!relay.configured || relay.output == state) return;
    gpio_set_level(relay.pin, relay.active_low ? !state : state);
    relay.output = state;
    if (callback_) callback_(index + 1, state, reason);
}

void RelayController::tick(int64_t now_us)
{
    xSemaphoreTake(mutex_, portMAX_DELAY);
    for (Zone &zone : zones_) {
        if (!zone.configured || !zone.enabled || zone.raw == zone.stable) continue;
        const float delay = zone.raw ? activation_seconds_ : deactivation_seconds_;
        if (now_us - zone.raw_changed_at_us >= static_cast<int64_t>(delay * 1'000'000.0f)) {
            zone.stable = zone.raw;
        }
    }

    bool automatic[kMaxRelays] = {};
    for (const Zone &zone : zones_) {
        if (!zone.configured || !zone.enabled || !zone.stable) continue;
        for (int relay = 0; relay < kMaxRelays; ++relay) {
            automatic[relay] = automatic[relay] || ((zone.relay_mask & (1u << relay)) != 0);
        }
    }

    const bool stale = stale_locked(now_us);
    for (int index = 0; index < kMaxRelays; ++index) {
        Relay &relay = relays_[index];
        if (!relay.configured) continue;
        if (relay.override_active && now_us >= relay.override_until_us) {
            relay.override_active = false;
        }
        bool desired = relay.output;
        const char *reason = "hold";
        if (emergency_) {
            desired = false;
            reason = "emergency";
        } else if (stale) {
            desired = false;
            reason = "stale_safe_off";
        } else if (!link_connected_ || last_heartbeat_us_ == 0) {
            desired = relay.output;
            reason = "link_freeze";
        } else if (relay.override_active) {
            desired = relay.override_state;
            reason = "manual_override";
        } else {
            desired = automatic[index];
            reason = "automatic_occupancy";
        }
        relay.mode = reason;
        write_relay_locked(index, desired, reason);
    }
    xSemaphoreGive(mutex_);
}

bool RelayController::relay_state(int relay_id) const
{
    return relay_id >= 1 && relay_id <= kMaxRelays && relays_[relay_id - 1].output;
}

bool RelayController::zone_state(int zone_id) const
{
    return zone_id >= 1 && zone_id <= kMaxZones && zones_[zone_id - 1].stable;
}

int RelayController::relay_gpio_level(int relay_id) const
{
    if (relay_id < 1 || relay_id > kMaxRelays || !relays_[relay_id - 1].configured) return -1;
    const Relay &relay = relays_[relay_id - 1];
    return relay.active_low ? !relay.output : relay.output;
}

const char *RelayController::relay_mode(int relay_id) const
{
    if (relay_id < 1 || relay_id > kMaxRelays || !relays_[relay_id - 1].configured) return "unconfigured";
    return relays_[relay_id - 1].mode;
}
