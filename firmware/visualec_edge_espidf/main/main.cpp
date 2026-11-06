#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <list>
#include <string>

#include "cJSON.h"
#include "dl_image_define.hpp"
#include "driver/gpio.h"
#include "esp_event.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_rom_crc.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_websocket_client.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "pedestrian_detect.hpp"
#if CONFIG_VISUALEC_USE_CUSTOM_MODEL
#include "visualec_pico_detect.hpp"
#endif

#include "relay_controller.hpp"
#include "wifi_provisioner.hpp"

namespace {

constexpr char kTag[] = "visualec_edge";
static EdgeNetworkConfig g_net_config;
constexpr uint8_t kFrameVersion = 1;
constexpr uint8_t kRgb565Le = 1;
constexpr size_t kFrameHeaderSize = 28;
constexpr size_t kMaxFrameWidth = 288;
constexpr size_t kMaxFrameHeight = 160;
constexpr size_t kMaxFramePixels = kMaxFrameWidth * kMaxFrameHeight * 2;
constexpr size_t kMaxWebsocketPayloadSize = kFrameHeaderSize + kMaxFramePixels;

struct FramePacket {
    uint32_t frame_id;
    uint64_t capture_timestamp_us;
    uint16_t width;
    uint16_t height;
    uint8_t *pixels;
    size_t pixel_bytes;
    int slot_index;
};

struct FrameSlot {
    FramePacket packet;
    uint8_t *pixel_buffer;
    bool in_use;
};

struct RelayChange {
    int relay_id;
    bool state;
    char reason[32];
};

RelayController g_relays;
QueueHandle_t g_frame_queue = nullptr;
QueueHandle_t g_relay_event_queue = nullptr;
SemaphoreHandle_t g_send_mutex = nullptr;
esp_websocket_client_handle_t g_websocket = nullptr;
bool g_websocket_connected = false;
uint32_t g_configuration_revision = 0;
float g_confidence_threshold = 0.45f;
uint8_t *g_fragment_buffer = nullptr;
size_t g_fragment_length = 0;
size_t g_fragment_received = 0;
uint8_t g_fragment_opcode = 0;
nvs_handle_t g_nvs = 0;
volatile bool g_occupancy_dirty = false;
static FrameSlot s_frame_slots[2] = {};

uint16_t read_u16_le(const uint8_t *data)
{
    return static_cast<uint16_t>(data[0]) | (static_cast<uint16_t>(data[1]) << 8);
}

uint32_t read_u32_le(const uint8_t *data)
{
    return static_cast<uint32_t>(data[0]) | (static_cast<uint32_t>(data[1]) << 8) |
           (static_cast<uint32_t>(data[2]) << 16) | (static_cast<uint32_t>(data[3]) << 24);
}

uint64_t read_u64_le(const uint8_t *data)
{
    return static_cast<uint64_t>(read_u32_le(data)) | (static_cast<uint64_t>(read_u32_le(data + 4)) << 32);
}

inline uint32_t crc32_standard(const uint8_t *data, size_t length)
{
    // Hardware ROM CRC32 lookup tables: reduces CRC calculation from ~40 ms to ~1 ms
    return esp_rom_crc32_le(0, data, length);
}

bool send_json(cJSON *document)
{
    if (!g_websocket_connected || !g_websocket || !document ||
        !esp_websocket_client_is_connected(g_websocket)) return false;
    char *encoded = cJSON_PrintUnformatted(document);
    if (!encoded) return false;
    xSemaphoreTake(g_send_mutex, portMAX_DELAY);
    const int result = esp_websocket_client_send_text(g_websocket, encoded, strlen(encoded), pdMS_TO_TICKS(3000));
    xSemaphoreGive(g_send_mutex);
    cJSON_free(encoded);
    return result >= 0;
}

void send_error(const char *code, const char *message)
{
    cJSON *document = cJSON_CreateObject();
    cJSON_AddStringToObject(document, "type", "error");
    cJSON_AddStringToObject(document, "code", code);
    cJSON_AddStringToObject(document, "message", message);
    send_json(document);
    cJSON_Delete(document);
}

void send_ack(const char *command_id, int relay_id = 0, const char *requested_state = nullptr)
{
    cJSON *document = cJSON_CreateObject();
    cJSON_AddStringToObject(document, "type", "ack");
    cJSON_AddStringToObject(document, "command_id", command_id ? command_id : "");
    cJSON_AddBoolToObject(document, "success", true);
    cJSON_AddNumberToObject(document, "configuration_revision", g_configuration_revision);
    if (relay_id > 0) {
        const bool state = g_relays.relay_state(relay_id);
        cJSON_AddNumberToObject(document, "relay_id", relay_id);
        cJSON_AddStringToObject(document, "requested_state", requested_state ? requested_state : (state ? "on" : "off"));
        cJSON_AddStringToObject(document, "effective_state", state ? "on" : "off");
        cJSON_AddNumberToObject(document, "gpio_level", g_relays.relay_gpio_level(relay_id));
        cJSON_AddStringToObject(document, "mode", g_relays.relay_mode(relay_id));
    }
    send_json(document);
    cJSON_Delete(document);
}

void relay_changed(int relay_id, bool state, const char *reason)
{
    RelayChange change = {.relay_id = relay_id, .state = state, .reason = {}};
    strlcpy(change.reason, reason, sizeof(change.reason));
    xQueueSend(g_relay_event_queue, &change, 0);
}

void send_relay_change(const RelayChange &change)
{
    cJSON *document = cJSON_CreateObject();
    cJSON_AddStringToObject(document, "type", "relay_event");
    cJSON_AddNumberToObject(document, "relay_id", change.relay_id);
    cJSON_AddStringToObject(document, "effective_state", change.state ? "on" : "off");
    cJSON_AddStringToObject(document, "reason", change.reason);
    cJSON_AddNumberToObject(document, "timestamp_us", static_cast<double>(esp_timer_get_time()));
    send_json(document);
    cJSON_Delete(document);
}

void send_occupancy_state()
{
    cJSON *document = cJSON_CreateObject();
    cJSON_AddStringToObject(document, "type", "occupancy_state");
    cJSON_AddNumberToObject(document, "configuration_revision", g_configuration_revision);
    cJSON *zones = cJSON_AddArrayToObject(document, "zones");
    for (int zone_id = 1; zone_id <= RelayController::kMaxZones; ++zone_id) {
        cJSON *item = cJSON_CreateObject();
        cJSON_AddNumberToObject(item, "zone_id", zone_id);
        cJSON_AddBoolToObject(item, "occupied", g_relays.zone_state(zone_id));
        cJSON_AddItemToArray(zones, item);
    }
    send_json(document);
    cJSON_Delete(document);
}

void persist_config(const char *json)
{
    if (!g_nvs || !json) return;
    nvs_set_str(g_nvs, "edge_config", json);
    nvs_set_u32(g_nvs, "config_rev", g_configuration_revision);
    nvs_commit(g_nvs);
}

void handle_config(cJSON *message, const char *raw_json, bool persist)
{
    const cJSON *revision = cJSON_GetObjectItemCaseSensitive(message, "revision");
    if (cJSON_IsNumber(revision) && revision->valuedouble < g_configuration_revision) {
        send_error("stale_config", "configuration revision is older than the active revision");
        return;
    }
    if (cJSON_IsNumber(revision)) g_configuration_revision = static_cast<uint32_t>(revision->valuedouble);
    const cJSON *activation = cJSON_GetObjectItemCaseSensitive(message, "activation_delay_seconds");
    const cJSON *deactivation = cJSON_GetObjectItemCaseSensitive(message, "deactivation_delay_seconds");
    const cJSON *stale = cJSON_GetObjectItemCaseSensitive(message, "camera_loss_timeout_seconds");
    const cJSON *confidence = cJSON_GetObjectItemCaseSensitive(message, "confidence_threshold");
    g_relays.configure_delays(
        cJSON_IsNumber(activation) ? activation->valuedouble : 1.0,
        cJSON_IsNumber(deactivation) ? deactivation->valuedouble : 10.0,
        cJSON_IsNumber(stale) ? stale->valuedouble : 30.0);
    if (cJSON_IsNumber(confidence)) g_confidence_threshold = confidence->valuedouble;

    const cJSON *relays = cJSON_GetObjectItemCaseSensitive(message, "relays");
    if (cJSON_IsArray(relays)) {
        const cJSON *item = nullptr;
        cJSON_ArrayForEach(item, relays) {
            const cJSON *id = cJSON_GetObjectItemCaseSensitive(item, "id");
            const cJSON *pin = cJSON_GetObjectItemCaseSensitive(item, "gpio_pin");
            const cJSON *active_low = cJSON_GetObjectItemCaseSensitive(item, "active_low");
            if (cJSON_IsNumber(id) && cJSON_IsNumber(pin)) {
                g_relays.configure_relay(id->valueint, pin->valueint, !cJSON_IsBool(active_low) || cJSON_IsTrue(active_low));
            }
        }
    }

    const cJSON *zones = cJSON_GetObjectItemCaseSensitive(message, "zones");
    if (cJSON_IsArray(zones)) {
        const cJSON *zone = nullptr;
        cJSON_ArrayForEach(zone, zones) {
            const cJSON *id = cJSON_GetObjectItemCaseSensitive(zone, "id");
            const cJSON *enabled = cJSON_GetObjectItemCaseSensitive(zone, "enabled");
            const cJSON *auto_control = cJSON_GetObjectItemCaseSensitive(zone, "auto_control_enabled");
            const cJSON *relay_ids = cJSON_GetObjectItemCaseSensitive(zone, "relay_ids");
            if (!cJSON_IsNumber(id) || !cJSON_IsArray(relay_ids)) continue;
            uint32_t relay_mask = 0;
            const cJSON *relay_id = nullptr;
            cJSON_ArrayForEach(relay_id, relay_ids) {
                if (cJSON_IsNumber(relay_id) && relay_id->valueint >= 1 && relay_id->valueint <= RelayController::kMaxRelays) {
                    relay_mask |= 1u << (relay_id->valueint - 1);
                }
            }
            const bool active = (!cJSON_IsBool(enabled) || cJSON_IsTrue(enabled)) &&
                                (!cJSON_IsBool(auto_control) || cJSON_IsTrue(auto_control));
            g_relays.configure_zone(id->valueint, relay_mask, active);
        }
    }
    if (persist && raw_json) persist_config(raw_json);
    ESP_LOGI(kTag, "Applied configuration revision %lu", static_cast<unsigned long>(g_configuration_revision));
}

void handle_occupancy(cJSON *message)
{
    const int64_t now = esp_timer_get_time();
    const cJSON *revision = cJSON_GetObjectItemCaseSensitive(message, "configuration_revision");
    if (!cJSON_IsNumber(revision) || static_cast<uint32_t>(revision->valuedouble) != g_configuration_revision) {
        send_error("configuration_revision_mismatch", "occupancy revision does not match active device configuration");
        return;
    }
    const cJSON *zones = cJSON_GetObjectItemCaseSensitive(message, "zones");
    if (!cJSON_IsArray(zones)) return;
    const cJSON *zone = nullptr;
    cJSON_ArrayForEach(zone, zones) {
        const cJSON *id = cJSON_GetObjectItemCaseSensitive(zone, "zone_id");
        const cJSON *occupied = cJSON_GetObjectItemCaseSensitive(zone, "occupied");
        if (cJSON_IsNumber(id) && cJSON_IsBool(occupied)) {
            g_relays.update_zone(id->valueint, cJSON_IsTrue(occupied), now);
        }
    }
    g_relays.note_occupancy_heartbeat(now);
}

void handle_text_message(const char *text, size_t length)
{
    cJSON *message = cJSON_ParseWithLength(text, length);
    if (!message) {
        send_error("invalid_json", "device could not parse the backend JSON message");
        return;
    }
    const cJSON *type = cJSON_GetObjectItemCaseSensitive(message, "type");
    const cJSON *command_id = cJSON_GetObjectItemCaseSensitive(message, "command_id");
    const char *command = cJSON_IsString(command_id) ? command_id->valuestring : "";
    if (cJSON_IsString(type) && strcmp(type->valuestring, "config") == 0) {
        std::string raw(text, length);
        handle_config(message, raw.c_str(), true);
    } else if (cJSON_IsString(type) && strcmp(type->valuestring, "occupancy") == 0) {
        handle_occupancy(message);
    } else if (cJSON_IsString(type) && strcmp(type->valuestring, "manual_override") == 0) {
        const cJSON *relay_id = cJSON_GetObjectItemCaseSensitive(message, "relay_id");
        const cJSON *state = cJSON_GetObjectItemCaseSensitive(message, "state");
        const cJSON *duration = cJSON_GetObjectItemCaseSensitive(message, "duration_seconds");
        if (cJSON_IsNumber(relay_id) && cJSON_IsString(state) && cJSON_IsNumber(duration)) {
            g_relays.manual_override(relay_id->valueint, strcmp(state->valuestring, "on") == 0, duration->valuedouble, esp_timer_get_time());
            send_ack(command, relay_id->valueint, state->valuestring);
        }
    } else if (cJSON_IsString(type) && strcmp(type->valuestring, "manual_override_cancel") == 0) {
        const cJSON *relay_id = cJSON_GetObjectItemCaseSensitive(message, "relay_id");
        if (cJSON_IsNumber(relay_id)) {
            g_relays.cancel_override(relay_id->valueint);
            g_relays.tick(esp_timer_get_time());
            send_ack(command, relay_id->valueint, "automatic");
        }
    } else if (cJSON_IsString(type) && strcmp(type->valuestring, "emergency") == 0) {
        const cJSON *active = cJSON_GetObjectItemCaseSensitive(message, "active");
        if (cJSON_IsBool(active)) {
            g_relays.set_emergency(cJSON_IsTrue(active));
            nvs_set_u8(g_nvs, "emergency", cJSON_IsTrue(active) ? 1 : 0);
            nvs_commit(g_nvs);
            g_relays.tick(esp_timer_get_time());
            send_ack(command);
        }
    } else if (cJSON_IsString(type) && strcmp(type->valuestring, "relay_command") == 0) {
        const cJSON *relay_id = cJSON_GetObjectItemCaseSensitive(message, "relay_id");
        const cJSON *state = cJSON_GetObjectItemCaseSensitive(message, "state");
        if (cJSON_IsNumber(relay_id) && cJSON_IsString(state)) {
            g_relays.manual_override(relay_id->valueint, strcmp(state->valuestring, "on") == 0, 0.25f, esp_timer_get_time());
            send_ack(command, relay_id->valueint, state->valuestring);
        }
    }
    cJSON_Delete(message);
}

void enqueue_frame(const uint8_t *packet, size_t length)
{
    if (length < kFrameHeaderSize || memcmp(packet, "VEC1", 4) != 0 || packet[4] != kFrameVersion || packet[5] != kRgb565Le) {
        send_error("invalid_frame_header", "unsupported binary frame header");
        return;
    }
    const uint16_t width = read_u16_le(packet + 20);
    const uint16_t height = read_u16_le(packet + 22);
    const size_t pixel_bytes = static_cast<size_t>(width) * height * 2;
    if (length != kFrameHeaderSize + pixel_bytes || pixel_bytes > kMaxFramePixels ||
        read_u32_le(packet + 24) != crc32_standard(packet + kFrameHeaderSize, pixel_bytes)) {
        send_error("invalid_frame_crc", "binary frame length or CRC does not match its header");
        return;
    }

    // Ping-pong buffer slot assignment: zero runtime malloc/free
    int slot_idx = -1;
    for (int i = 0; i < 2; ++i) {
        if (!s_frame_slots[i].in_use) {
            slot_idx = i;
            break;
        }
    }

    // If both slots are in use (inference running and previous frame still queued),
    // drop the stale queued frame so we process the freshest one with zero queue latency
    if (slot_idx < 0) {
        FramePacket *stale = nullptr;
        if (xQueueReceive(g_frame_queue, &stale, 0) == pdTRUE && stale) {
            if (stale->slot_index >= 0 && stale->slot_index < 2) {
                s_frame_slots[stale->slot_index].in_use = false;
                slot_idx = stale->slot_index;
            }
        }
    }

    if (slot_idx < 0) {
        // Still busy; drop frame to prevent backpressure
        return;
    }

    FrameSlot &slot = s_frame_slots[slot_idx];
    slot.in_use = true;
    memcpy(slot.pixel_buffer, packet + kFrameHeaderSize, pixel_bytes);
    slot.packet.frame_id = read_u32_le(packet + 8);
    slot.packet.capture_timestamp_us = read_u64_le(packet + 12);
    slot.packet.width = width;
    slot.packet.height = height;
    slot.packet.pixels = slot.pixel_buffer;
    slot.packet.pixel_bytes = pixel_bytes;
    slot.packet.slot_index = slot_idx;

    FramePacket *frame_ptr = &slot.packet;
    if (xQueueSend(g_frame_queue, &frame_ptr, 0) != pdTRUE) {
        slot.in_use = false;
    }
}

void reset_fragment_buffer()
{
    g_fragment_length = 0;
    g_fragment_received = 0;
    g_fragment_opcode = 0;
}

void handle_websocket_payload(esp_websocket_event_data_t *data)
{
    if (!data || data->payload_len < 0 || data->data_len < 0 || data->payload_offset < 0) return;
    // Silently ignore RFC 6455 control frames (0x8 Close, 0x9 Ping, 0xA Pong) or empty keepalives
    if (data->op_code == 0x8 || data->op_code == 0x9 || data->op_code == 0xA || data->payload_len == 0) return;

    const size_t total_length = static_cast<size_t>(data->payload_len);
    const size_t chunk_length = static_cast<size_t>(data->data_len);
    const size_t offset = static_cast<size_t>(data->payload_offset);
    if (total_length > kMaxWebsocketPayloadSize ||
        offset > total_length || chunk_length > total_length - offset) {
        reset_fragment_buffer();
        send_error("invalid_websocket_payload", "WebSocket payload length is outside the supported range");
        return;
    }

    // Fast path: unfragmented payload (zero reassembly copy)
    if (offset == 0 && chunk_length == total_length) {
        reset_fragment_buffer();
        if (data->op_code == 0x1) handle_text_message(data->data_ptr, chunk_length);
        else if (data->op_code == 0x2) enqueue_frame(reinterpret_cast<const uint8_t *>(data->data_ptr), chunk_length);
        return;
    }

    // Fragmented payload: reassemble into preallocated static PSRAM buffer (zero malloc/free)
    if (offset == 0) {
        reset_fragment_buffer();
        if (!g_fragment_buffer) {
            send_error("payload_allocation_failed", "Static fragment buffer not initialized");
            return;
        }
        g_fragment_length = total_length;
        g_fragment_opcode = data->op_code;
    }
    if (!g_fragment_buffer || total_length != g_fragment_length || offset != g_fragment_received) {
        reset_fragment_buffer();
        send_error("invalid_websocket_fragment", "WebSocket fragments arrived out of sequence");
        return;
    }

    memcpy(g_fragment_buffer + offset, data->data_ptr, chunk_length);
    g_fragment_received += chunk_length;
    if (g_fragment_received == g_fragment_length) {
        if (g_fragment_opcode == 0x1) {
            handle_text_message(reinterpret_cast<const char *>(g_fragment_buffer), g_fragment_length);
        } else if (g_fragment_opcode == 0x2) {
            enqueue_frame(g_fragment_buffer, g_fragment_length);
        }
        reset_fragment_buffer();
    }
}

void send_hello()
{
    cJSON *document = cJSON_CreateObject();
    cJSON_AddStringToObject(document, "type", "hello");
    cJSON_AddNumberToObject(document, "protocol", 1);
    cJSON_AddStringToObject(document, "device_id", CONFIG_VISUALEC_DEVICE_ID);
    cJSON_AddStringToObject(document, "firmware_version", CONFIG_VISUALEC_FIRMWARE_VERSION);
    cJSON_AddStringToObject(document, "model_version", CONFIG_VISUALEC_MODEL_VERSION);
    cJSON_AddStringToObject(document, "model_sha256", CONFIG_VISUALEC_MODEL_SHA256);
    cJSON_AddNumberToObject(document, "configuration_revision", g_configuration_revision);
    cJSON_AddNumberToObject(document, "input_width", 288);
    cJSON_AddNumberToObject(document, "input_height", 160);
#if CONFIG_VISUALEC_USE_CUSTOM_MODEL
    cJSON_AddNumberToObject(document, "model_input_width", 288);
    cJSON_AddNumberToObject(document, "model_input_height", 160);
#else
    // The bootstrap pedestrian model is square. The backend preconditions the
    // rectangular wire frame so the ESP-DL resize does not stretch people.
    cJSON_AddNumberToObject(document, "model_input_width", 224);
    cJSON_AddNumberToObject(document, "model_input_height", 224);
#endif
    send_json(document);
    cJSON_Delete(document);
}

void websocket_event_handler(void *, esp_event_base_t, int32_t event_id, void *event_data)
{
    auto *data = static_cast<esp_websocket_event_data_t *>(event_data);
    if (event_id == WEBSOCKET_EVENT_CONNECTED) {
        g_websocket_connected = true;
        g_relays.set_link_connected(true, esp_timer_get_time());
        send_hello();
    } else if (event_id == WEBSOCKET_EVENT_DISCONNECTED ||
               event_id == WEBSOCKET_EVENT_CLOSED ||
               event_id == WEBSOCKET_EVENT_FINISH) {
        g_websocket_connected = false;
        reset_fragment_buffer();
        g_relays.set_link_connected(false, esp_timer_get_time());
    } else if (event_id == WEBSOCKET_EVENT_DATA && data) {
        handle_websocket_payload(data);
    }
}

void inference_task(void *)
{
#if CONFIG_VISUALEC_USE_CUSTOM_MODEL
    VisualecPicoDetect detector(false);
#else
    PedestrianDetect detector(PedestrianDetect::PICO_S8_V1, false);
#endif
    char json_buf[1024];
    while (true) {
        FramePacket *frame = nullptr;
        if (xQueueReceive(g_frame_queue, &frame, portMAX_DELAY) != pdTRUE || !frame) continue;
        const int64_t started = esp_timer_get_time();
        dl::image::img_t image = {
            .data = frame->pixels,
            .width = frame->width,
            .height = frame->height,
            .pix_type = dl::image::DL_IMAGE_PIX_TYPE_RGB565LE,
        };
        detector.set_score_thr(g_confidence_threshold);
        std::list<dl::detect::result_t> &results = detector.run(image);
        const float elapsed_ms = static_cast<float>(esp_timer_get_time() - started) / 1000.0f;

        // Zero-allocation JSON formatting directly into stack buffer for minimal latency
        int written = snprintf(json_buf, sizeof(json_buf),
            "{\"type\":\"inference_result\",\"frame_id\":%lu,\"capture_timestamp_us\":%llu,\"inference_ms\":%.2f,\"detections\":[",
            static_cast<unsigned long>(frame->frame_id),
            static_cast<unsigned long long>(frame->capture_timestamp_us),
            elapsed_ms);
        bool first = true;
        for (const auto &result : results) {
            if (result.score < g_confidence_threshold || result.box.size() < 4) continue;
            if (!first) {
                written += snprintf(json_buf + written, sizeof(json_buf) - written, ",");
            }
            first = false;
            written += snprintf(json_buf + written, sizeof(json_buf) - written,
                "{\"confidence\":%.3f,\"bbox\":[%d,%d,%d,%d]}",
                result.score, result.box[0], result.box[1], result.box[2], result.box[3]);
            if (written >= static_cast<int>(sizeof(json_buf)) - 32) break;
        }
        written += snprintf(json_buf + written, sizeof(json_buf) - written, "]}");

        xSemaphoreTake(g_send_mutex, portMAX_DELAY);
        if (g_websocket_connected && g_websocket && esp_websocket_client_is_connected(g_websocket)) {
            esp_websocket_client_send_text(g_websocket, json_buf, written, pdMS_TO_TICKS(1000));
        }
        xSemaphoreGive(g_send_mutex);

        // Mark preallocated ping-pong slot available immediately with zero heap overhead
        if (frame->slot_index >= 0 && frame->slot_index < 2) {
            s_frame_slots[frame->slot_index].in_use = false;
        }
    }
}

void control_task(void *)
{
    bool previous_zones[RelayController::kMaxZones] = {};
    while (true) {
        g_relays.tick(esp_timer_get_time());
        bool changed = false;
        for (int zone = 0; zone < RelayController::kMaxZones; ++zone) {
            const bool current = g_relays.zone_state(zone + 1);
            changed = changed || current != previous_zones[zone];
            previous_zones[zone] = current;
        }
        if (changed) g_occupancy_dirty = true;
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

void metrics_task(void *)
{
    int64_t next_metrics_at = 0;
    while (true) {
        RelayChange change = {};
        while (xQueueReceive(g_relay_event_queue, &change, 0) == pdTRUE) {
            send_relay_change(change);
        }
        if (g_occupancy_dirty) {
            g_occupancy_dirty = false;
            send_occupancy_state();
        }
        const int64_t now = esp_timer_get_time();
        if (g_websocket_connected && now >= next_metrics_at) {
            wifi_ap_record_t access_point = {};
            esp_wifi_sta_get_ap_info(&access_point);
            cJSON *document = cJSON_CreateObject();
            cJSON_AddStringToObject(document, "type", "metrics");
            cJSON_AddNumberToObject(document, "free_heap_bytes", heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
            cJSON_AddNumberToObject(document, "free_psram_bytes", heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
            cJSON_AddNumberToObject(document, "wifi_rssi", access_point.rssi);
            cJSON_AddNumberToObject(document, "configuration_revision", g_configuration_revision);
            send_json(document);
            cJSON_Delete(document);
            next_metrics_at = now + 2'000'000;
        }
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

void wifi_event_handler(void *, esp_event_base_t event_base, int32_t event_id, void *event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        ESP_LOGI(kTag, "Wi-Fi Station started, connecting to '%s'...", g_net_config.ssid.c_str());
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(kTag, "Wi-Fi disconnected. Reconnecting...");
        esp_wifi_connect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = static_cast<ip_event_got_ip_t *>(event_data);
        ESP_LOGI(kTag, "Wi-Fi connected! Station IP: " IPSTR, IP2STR(&event->ip_info.ip));
    }
}

void initialise_wifi()
{
    load_edge_network_config(g_net_config);

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    // Create both Station (connects to your router) and SoftAP (setup web portal) interfaces
    esp_netif_create_default_wifi_sta();
    esp_netif_create_default_wifi_ap();

    wifi_init_config_t config = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&config));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event_handler, nullptr));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event_handler, nullptr));

    // 1. SoftAP Setup: "Visualec-Setup" (IP 192.168.4.1) for local web configuration
    wifi_config_t ap_config = {};
    strlcpy(reinterpret_cast<char *>(ap_config.ap.ssid), "Visualec-Setup", sizeof(ap_config.ap.ssid));
    ap_config.ap.ssid_len = strlen("Visualec-Setup");
    ap_config.ap.channel = 1;
    ap_config.ap.max_connection = 4;
    ap_config.ap.authmode = WIFI_AUTH_OPEN;

    // 2. Station Setup: connects to default "Xx" / "sarvesh@2643" (or NVS credentials)
    wifi_config_t sta_config = {};
    strlcpy(reinterpret_cast<char *>(sta_config.sta.ssid), g_net_config.ssid.c_str(), sizeof(sta_config.sta.ssid));
    strlcpy(reinterpret_cast<char *>(sta_config.sta.password), g_net_config.password.c_str(), sizeof(sta_config.sta.password));
    sta_config.sta.threshold.authmode = g_net_config.password.empty() ? WIFI_AUTH_OPEN : WIFI_AUTH_WPA2_PSK;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_APSTA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap_config));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &sta_config));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));

    // Start local web configuration server on port 80 (accessible on 192.168.4.1 or station IP)
    start_web_config_server(g_net_config);

    ESP_LOGI(kTag, "AP+STA mode active. Hotspot: 'Visualec-Setup' (192.168.4.1), connecting to '%s'", g_net_config.ssid.c_str());
}

void load_persisted_state()
{
    nvs_open("visualec", NVS_READWRITE, &g_nvs);
    uint8_t emergency = 0;
    nvs_get_u8(g_nvs, "emergency", &emergency);
    g_relays.set_emergency(emergency != 0);
    nvs_get_u32(g_nvs, "config_rev", &g_configuration_revision);
    size_t length = 0;
    if (nvs_get_str(g_nvs, "edge_config", nullptr, &length) == ESP_OK && length > 1) {
        char *json = static_cast<char *>(malloc(length));
        if (json && nvs_get_str(g_nvs, "edge_config", json, &length) == ESP_OK) {
            cJSON *document = cJSON_Parse(json);
            if (document) {
                handle_config(document, nullptr, false);
                cJSON_Delete(document);
            }
        }
        free(json);
    } else {
        g_relays.configure_relay(1, 4, true);
        g_relays.configure_relay(2, 5, true);
        g_relays.configure_relay(3, 18, true);
        g_relays.configure_zone(1, 1u << 0, true);
        g_relays.configure_zone(2, 1u << 1, true);
        g_relays.configure_zone(3, 1u << 2, true);
    }
}

void start_websocket()
{
    static std::string uri = g_net_config.ws_url + "?token=" + g_net_config.device_token;
    esp_websocket_client_config_t websocket_config = {};
    websocket_config.uri = uri.c_str();
    websocket_config.network_timeout_ms = 5000;
    websocket_config.reconnect_timeout_ms = 2000;
    websocket_config.enable_close_reconnect = true;
    websocket_config.task_stack = 8192;
    websocket_config.buffer_size = 32768; // 32 KB buffer to minimize fragmentation context switches
    websocket_config.task_prio = 10; // High networking priority (preempts control/inference for immediate packet processing)
    websocket_config.task_core_id_set = true;
    websocket_config.task_core_id = 0; // Pin WebSocket networking to Core 0
    g_websocket = esp_websocket_client_init(&websocket_config);
    ESP_ERROR_CHECK(esp_websocket_register_events(g_websocket, WEBSOCKET_EVENT_ANY, websocket_event_handler, nullptr));
    ESP_ERROR_CHECK(esp_websocket_client_start(g_websocket));
}

} // namespace

extern "C" void app_main(void)
{
    esp_err_t nvs_result = nvs_flash_init();
    if (nvs_result == ESP_ERR_NVS_NO_FREE_PAGES || nvs_result == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }

    // Preallocate fragment reassembly buffer and ping-pong frame buffers in PSRAM at boot
    g_fragment_buffer = static_cast<uint8_t *>(heap_caps_malloc(kMaxWebsocketPayloadSize, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    assert(g_fragment_buffer != nullptr);

    for (int i = 0; i < 2; ++i) {
        s_frame_slots[i].pixel_buffer = static_cast<uint8_t *>(heap_caps_malloc(kMaxFramePixels, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
        assert(s_frame_slots[i].pixel_buffer != nullptr);
        s_frame_slots[i].in_use = false;
    }

    g_send_mutex = xSemaphoreCreateMutex();
    g_frame_queue = xQueueCreate(1, sizeof(FramePacket *));
    g_relay_event_queue = xQueueCreate(8, sizeof(RelayChange));
    g_relays.begin(relay_changed);
    load_persisted_state();
    initialise_wifi();
    start_websocket();
    xTaskCreatePinnedToCore(control_task, "relay_control", 6144, nullptr, 9, nullptr, 0);
    xTaskCreatePinnedToCore(inference_task, "edge_inference", 12288, nullptr, 6, nullptr, 1);
    xTaskCreatePinnedToCore(metrics_task, "edge_metrics", 4096, nullptr, 3, nullptr, 0);
    ESP_LOGI(kTag, "Visualec edge firmware started; relays safe, waiting for authenticated occupancy");
}
