#pragma once
#include <stdbool.h>
#include "esp_err.h"

/* Start after GNSS initialization, from app_main only. Local UART0 test input
 * is opt-in: TEST_ALERT publishes; TEST_ALERT_BUZZER may arm the demo buzzer.
 */
esp_err_t device_telemetry_start(const char *device_id, bool enable_serial_test);
