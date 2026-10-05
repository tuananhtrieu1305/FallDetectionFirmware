idf_component_register(
    SRCS
        "app_main.c"
        "alert_manager.c"

    INCLUDE_DIRS
        "."

    PRIV_REQUIRES
        esp_driver_i2c
        esp_driver_gpio
        esp_driver_ledc
        esp_timer
        bmi270
)