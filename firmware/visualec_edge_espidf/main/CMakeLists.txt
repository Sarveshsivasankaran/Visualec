idf_component_register(
    SRCS "main.cpp" "relay_controller.cpp"
    INCLUDE_DIRS "."
    REQUIRES driver esp_driver_gpio esp_event esp_netif esp_timer esp_wifi nvs_flash pedestrian_detect visualec_pico esp_websocket_client
)
