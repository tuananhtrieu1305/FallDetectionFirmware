
idf_component_register(
    SRCS
        "app_main.c"
        "alert_manager.c"
        "sensor_manager.c"
        "sensor_bus.c"
        "gnss_manager.c"
        "lte_manager.c"
        "wifi_manager.c"
        "mqtt_manager.c"
        "device_telemetry.c"
        "command_processor.c"
        "device_clock.c"

    INCLUDE_DIRS
        "."

    PRIV_REQUIRES
        esp_driver_i2c
        esp_driver_gpio
        esp_driver_ledc
        esp_driver_uart
        esp_adc
        esp_timer
        esp_wifi
        esp_netif
        esp_event
        nvs_flash
        mqtt
        json
        heap
        bmi270
        bmp3
)

# Detect adding/removing the ignored header as well as edits to an existing one.
# Changing this source definition invalidates app_main.o, avoiding stale embedded
# credentials when a previously absent local header is created or removed.
file(GLOB network_local_config CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/network_config.local.h")
if(network_local_config)
    set_property(SOURCE app_main.c APPEND PROPERTY COMPILE_DEFINITIONS
        NETWORK_LOCAL_CONFIG_PRESENT=1)
else()
    set_property(SOURCE app_main.c APPEND PROPERTY COMPILE_DEFINITIONS
        NETWORK_LOCAL_CONFIG_PRESENT=0)
endif()
