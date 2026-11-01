#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

esp_err_t device_clock_init(const char *ntp_server);
void device_clock_poll(bool network_ready);
/* -1 without real SNTP or a fresh current GNSS fix; SNTP anchor expires after
 * one hour, GNSS after five seconds. Demo SNTP is
 * unauthenticated and is not a production authenticated clock authority.
 */
int64_t device_clock_now_ms(void);
