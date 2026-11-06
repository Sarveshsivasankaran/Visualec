#pragma once

#include <string>

struct EdgeNetworkConfig {
    std::string ssid;
    std::string password;
    std::string ws_url;
    std::string device_token;
};

constexpr char kDefaultWifiSsid[] = "Xx";
constexpr char kDefaultWifiPass[] = "sarvesh@2643";

// Loads network configuration from NVS ("visualec" namespace).
// Falls back to kDefaultWifiSsid ("Xx") and kDefaultWifiPass ("sarvesh@2643") if NVS is empty.
bool load_edge_network_config(EdgeNetworkConfig &out_config);

// Saves network configuration to NVS ("visualec" namespace).
bool save_edge_network_config(const EdgeNetworkConfig &config);

// Starts the local asynchronous HTTP web server on port 80 (non-blocking).
// Serves the setup web UI at "/" and handles POST "/save" to update credentials.
void start_web_config_server(const EdgeNetworkConfig &current_config);
