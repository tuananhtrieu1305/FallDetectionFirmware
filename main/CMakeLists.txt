idf_component_register(
    SRCS "app_main.c"
    PRIV_REQUIRES
        esp_driver_i2c
        bmi270
    INCLUDE_DIRS ""
)