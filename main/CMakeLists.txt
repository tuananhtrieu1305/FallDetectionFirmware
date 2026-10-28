
idf_component_register(
    SRCS
        "app_main.c"
        "alert_manager.c"
        "sensor_manager.c"
        "gnss_manager.c"
        "lte_manager.c"

    INCLUDE_DIRS
        "."

    PRIV_REQUIRES
        esp_driver_i2c
        esp_driver_gpio
        esp_driver_ledc
        esp_driver_uart
        esp_adc
        esp_timer
        heap
        bmi270
        bmp3
)
