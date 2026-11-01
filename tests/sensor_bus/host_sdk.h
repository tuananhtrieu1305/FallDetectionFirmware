#pragma once
#include "../mqtt_manager/host_sdk.h"
#define portMAX_DELAY UINT32_MAX
typedef struct {int unused;} i2c_master_bus_config_t;
typedef void *i2c_master_bus_handle_t;
int xPortGetCoreID(void);
TaskHandle_t xTaskGetCurrentTaskHandle(void);
esp_err_t i2c_new_master_bus(const i2c_master_bus_config_t *,i2c_master_bus_handle_t *);
