#include "wifi_provisioner.hpp"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include "driver/gpio.h"
#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs.h"
#include "nvs_flash.h"

namespace {

constexpr char kTag[] = "wifi_prov";
constexpr char kNvsNamespace[] = "visualec";
constexpr char kKeySsid[] = "wifi_ssid";
constexpr char kKeyPass[] = "wifi_pass";
constexpr char kKeyWsUrl[] = "ws_url";
constexpr char kKeyToken[] = "dev_token";

static httpd_handle_t s_server = nullptr;
static EdgeNetworkConfig s_current_config;

std::string url_decode(const std::string &in)
{
    std::string out;
    out.reserve(in.size());
    for (size_t i = 0; i < in.size(); ++i) {
        if (in[i] == '+') {
            out += ' ';
        } else if (in[i] == '%' && i + 2 < in.size()) {
            char hex[3] = {in[i + 1], in[i + 2], '\0'};
            char *end = nullptr;
            long val = strtol(hex, &end, 16);
            if (end == hex + 2) {
                out += static_cast<char>(val);
                i += 2;
            } else {
                out += in[i];
            }
        } else {
            out += in[i];
        }
    }
    return out;
}

std::string get_form_field(const std::string &body, const std::string &field)
{
    size_t pos = 0;
    while (pos < body.size()) {
        size_t eq = body.find('=', pos);
        if (eq == std::string::npos) break;
        size_t amp = body.find('&', eq);
        if (amp == std::string::npos) amp = body.size();
        std::string key = body.substr(pos, eq - pos);
        if (key == field) {
            return url_decode(body.substr(eq + 1, amp - eq - 1));
        }
        pos = amp + 1;
    }
    return "";
}

const char kPortalHtml[] = R"rawhtml(<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Visualec Edge Setup</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background-color: #0b0f19; color: #f3f4f6; display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 20px; }
    .card { background-color: #111827; border: 1px solid #1f2937; border-radius: 14px; padding: 28px; width: 100%; max-width: 440px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5); }
    .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid #1f2937; }
    .title { font-size: 20px; font-weight: 700; color: #60a5fa; }
    .badge { background-color: #1e3a5f; color: #93c5fd; font-size: 11px; padding: 4px 8px; border-radius: 9999px; font-weight: 600; text-transform: uppercase; }
    .desc { font-size: 13px; color: #9ca3af; margin-bottom: 20px; line-height: 1.5; }
    .field { margin-bottom: 16px; }
    label { display: block; font-size: 12px; font-weight: 600; color: #d1d5db; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.05em; }
    input[type="text"], input[type="password"] { width: 100%; padding: 10px 12px; background: #1f2937; border: 1px solid #374151; border-radius: 8px; color: #fff; font-size: 14px; outline: none; transition: border-color 0.2s; }
    input[type="text"]:focus, input[type="password"]:focus { border-color: #3b82f6; }
    .pw-wrap { position: relative; }
    .pw-toggle { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); background: none; border: none; color: #9ca3af; cursor: pointer; font-size: 12px; padding: 4px; }
    .btn { width: 100%; padding: 12px; background-color: #2563eb; color: white; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; transition: background-color 0.2s; margin-top: 8px; }
    .btn:hover { background-color: #1d4ed8; }
    .footer { margin-top: 20px; font-size: 11px; color: #6b7280; text-align: center; }
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="title">Visualec Edge</div>
      <span class="badge">Wi-Fi Setup</span>
    </div>
    <p class="desc">Configure 2.4 GHz Wi-Fi credentials and backend endpoint for the ESP32-S3 edge node.</p>
    <form action="/save" method="POST">
      <div class="field">
        <label for="ssid">Wi-Fi Network Name (SSID)</label>
        <input type="text" id="ssid" name="ssid" required placeholder="e.g. Xx" autofocus value="%SSID%">
      </div>
      <div class="field">
        <label for="password">Wi-Fi Password</label>
        <div class="pw-wrap">
          <input type="password" id="password" name="password" placeholder="Enter network password" value="%PASSWORD%">
          <button type="button" class="pw-toggle" onclick="var p=document.getElementById('password');if(p.type==='password'){p.type='text';this.textContent='Hide';}else{p.type='password';this.textContent='Show';}">Show</button>
        </div>
      </div>
      <div class="field">
        <label for="ws_url">Backend WebSocket URL</label>
        <input type="text" id="ws_url" name="ws_url" value="%WS_URL%">
      </div>
      <div class="field">
        <label for="token">Device Token</label>
        <input type="password" id="token" name="token" value="%TOKEN%">
      </div>
      <button type="submit" class="btn">Save & Connect</button>
    </form>
    <div class="footer">Setup Portal: <strong>Visualec-Setup</strong> (192.168.4.1)</div>
  </div>
</body>
</html>)rawhtml";

const char kSavedHtml[] = R"rawhtml(<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Configuration Saved</title>
  <style>
    body { background-color: #0b0f19; color: #f3f4f6; font-family: -apple-system, BlinkMacSystemFont, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }
    .card { background-color: #111827; border: 1px solid #1f2937; border-radius: 14px; padding: 32px; max-width: 420px; text-align: center; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5); }
    h2 { color: #10b981; font-size: 22px; margin-bottom: 12px; }
    p { color: #9ca3af; font-size: 14px; line-height: 1.6; margin-bottom: 20px; }
    .spinner { border: 3px solid #1f2937; border-top: 3px solid #3b82f6; border-radius: 50%; width: 36px; height: 36px; animation: spin 1s linear infinite; margin: 0 auto; }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="card">
    <h2>✓ Settings Saved</h2>
    <p>The ESP32-S3 is restarting now and connecting to your Wi-Fi network.<br><br>The <strong>Visualec-Setup</strong> access point will close.</p>
    <div class="spinner"></div>
  </div>
</body>
</html>)rawhtml";

void delayed_restart_task(void *)
{
    vTaskDelay(pdMS_TO_TICKS(1500));
    ESP_LOGI(kTag, "Rebooting device with new network configuration...");
    esp_restart();
}

esp_err_t root_get_handler(httpd_req_t *req)
{
    std::string page = kPortalHtml;

    size_t pos_ssid = page.find("%SSID%");
    if (pos_ssid != std::string::npos) {
        page.replace(pos_ssid, 6, s_current_config.ssid);
    }
    size_t pos_pass = page.find("%PASSWORD%");
    if (pos_pass != std::string::npos) {
        page.replace(pos_pass, 10, s_current_config.password);
    }
    size_t pos_ws = page.find("%WS_URL%");
    if (pos_ws != std::string::npos) {
        page.replace(pos_ws, 8, s_current_config.ws_url.empty() ? CONFIG_VISUALEC_BACKEND_WS_URL : s_current_config.ws_url);
    }
    size_t pos_tok = page.find("%TOKEN%");
    if (pos_tok != std::string::npos) {
        page.replace(pos_tok, 7, s_current_config.device_token.empty() ? CONFIG_VISUALEC_DEVICE_TOKEN : s_current_config.device_token);
    }

    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, page.c_str(), page.length());
}

esp_err_t captive_redirect_handler(httpd_req_t *req)
{
    httpd_resp_set_status(req, "302 Found");
    httpd_resp_set_hdr(req, "Location", "http://192.168.4.1/");
    return httpd_resp_send(req, nullptr, 0);
}

esp_err_t save_post_handler(httpd_req_t *req)
{
    char buf[1024] = {};
    int received = 0;
    int remaining = req->content_len;

    if (remaining >= static_cast<int>(sizeof(buf))) {
        httpd_resp_send_500(req);
        return ESP_FAIL;
    }

    while (remaining > 0) {
        int ret = httpd_req_recv(req, buf + received, remaining);
        if (ret <= 0) {
            if (ret == HTTPD_SOCK_ERR_TIMEOUT) continue;
            return ESP_FAIL;
        }
        received += ret;
        remaining -= ret;
    }
    buf[received] = '\0';

    std::string body(buf);
    std::string ssid = get_form_field(body, "ssid");
    std::string pass = get_form_field(body, "password");
    std::string ws_url = get_form_field(body, "ws_url");
    std::string token = get_form_field(body, "token");

    if (ssid.empty()) {
        const char *err = "SSID cannot be empty.";
        httpd_resp_set_status(req, "400 Bad Request");
        httpd_resp_send(req, err, strlen(err));
        return ESP_OK;
    }

    EdgeNetworkConfig cfg;
    cfg.ssid = ssid;
    cfg.password = pass;
    cfg.ws_url = ws_url.empty() ? CONFIG_VISUALEC_BACKEND_WS_URL : ws_url;
    cfg.device_token = token.empty() ? CONFIG_VISUALEC_DEVICE_TOKEN : token;

    if (!save_edge_network_config(cfg)) {
        httpd_resp_send_500(req);
        return ESP_FAIL;
    }

    ESP_LOGI(kTag, "Saved new Wi-Fi credentials for SSID: '%s'", cfg.ssid.c_str());

    httpd_resp_set_type(req, "text/html");
    httpd_resp_send(req, kSavedHtml, strlen(kSavedHtml));

    xTaskCreate(delayed_restart_task, "restart_task", 2048, nullptr, 5, nullptr);
    return ESP_OK;
}

} // namespace

bool load_edge_network_config(EdgeNetworkConfig &out_config)
{
    nvs_handle_t nvs = 0;
    esp_err_t err = nvs_open(kNvsNamespace, NVS_READONLY, &nvs);
    if (err == ESP_OK) {
        char buf[256] = {};
        size_t len = sizeof(buf);

        if (nvs_get_str(nvs, kKeySsid, buf, &len) == ESP_OK && len > 1) {
            out_config.ssid = buf;
        }

        len = sizeof(buf);
        if (nvs_get_str(nvs, kKeyPass, buf, &len) == ESP_OK) {
            out_config.password = buf;
        }

        len = sizeof(buf);
        if (nvs_get_str(nvs, kKeyWsUrl, buf, &len) == ESP_OK && len > 1) {
            out_config.ws_url = buf;
        }

        len = sizeof(buf);
        if (nvs_get_str(nvs, kKeyToken, buf, &len) == ESP_OK && len > 1) {
            out_config.device_token = buf;
        }

        nvs_close(nvs);
    }

    // Default to "Xx" and "sarvesh@2643" if not configured in NVS
    if (out_config.ssid.empty()) {
        out_config.ssid = kDefaultWifiSsid;
        out_config.password = kDefaultWifiPass;
    }
    if (out_config.ws_url.empty() || out_config.ws_url.find("172.16.11.87") != std::string::npos || out_config.ws_url.find("10.57.98.1") != std::string::npos) {
        out_config.ws_url = "ws://10.182.241.125:8000/ws/edge";
    }
    if (out_config.device_token.empty()) {
        out_config.device_token = CONFIG_VISUALEC_DEVICE_TOKEN;
    }

    return true;
}

bool save_edge_network_config(const EdgeNetworkConfig &config)
{
    nvs_handle_t nvs = 0;
    esp_err_t err = nvs_open(kNvsNamespace, NVS_READWRITE, &nvs);
    if (err != ESP_OK) return false;

    nvs_set_str(nvs, kKeySsid, config.ssid.c_str());
    nvs_set_str(nvs, kKeyPass, config.password.c_str());
    nvs_set_str(nvs, kKeyWsUrl, config.ws_url.c_str());
    nvs_set_str(nvs, kKeyToken, config.device_token.c_str());
    nvs_commit(nvs);
    nvs_close(nvs);
    return true;
}

void start_web_config_server(const EdgeNetworkConfig &current_config)
{
    s_current_config = current_config;

    httpd_config_t server_config = HTTPD_DEFAULT_CONFIG();
    server_config.max_uri_handlers = 8;
    server_config.stack_size = 4096;

    if (httpd_start(&s_server, &server_config) == ESP_OK) {
        httpd_uri_t root_uri = {
            .uri = "/",
            .method = HTTP_GET,
            .handler = root_get_handler,
            .user_ctx = nullptr
        };
        httpd_register_uri_handler(s_server, &root_uri);

        httpd_uri_t save_uri = {
            .uri = "/save",
            .method = HTTP_POST,
            .handler = save_post_handler,
            .user_ctx = nullptr
        };
        httpd_register_uri_handler(s_server, &save_uri);

        const char *redirect_paths[] = {
            "/generate_204",
            "/hotspot-detect.html",
            "/ncsi.txt",
            "/connecttest.txt"
        };
        for (const char *path : redirect_paths) {
            httpd_uri_t redir_uri = {
                .uri = path,
                .method = HTTP_GET,
                .handler = captive_redirect_handler,
                .user_ctx = nullptr
            };
            httpd_register_uri_handler(s_server, &redir_uri);
        }
        ESP_LOGI(kTag, "Web configuration server listening on port 80 (http://192.168.4.1/ or station IP)");
    } else {
        ESP_LOGE(kTag, "Failed to start HTTP configuration server");
    }
}
