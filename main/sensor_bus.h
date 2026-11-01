#pragma once
#include "driver/i2c_master.h"

/* Boot-only, before sensor acquisition: allocate I2C IRQ on core1. Bus config,
 * device clocks/GPIOs and all subsequent Bosch operations remain unchanged.
 */
esp_err_t sensor_bus_create(const i2c_master_bus_config_t *config, i2c_master_bus_handle_t *out);
