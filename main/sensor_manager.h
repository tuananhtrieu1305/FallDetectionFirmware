#pragma once
#include "esp_err.h"
#include "bmi270.h"
#include "bmp3.h"

/* Starts the periodic BMI270 task. BMP3 is retained for PHASE 5.4.
 * Must be called only once AFTER both Bosch drivers are configured.
 * Driver objects must remain valid for the lifetime of the task.
 */
esp_err_t sensor_manager_start(struct bmi2_dev *bmi, struct bmp3_dev *bmp);
