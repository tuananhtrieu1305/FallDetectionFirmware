#pragma once

#include "esp_err.h"

/* Start a separate UART2 task for the Phase 7 AT-only check. */
esp_err_t lte_manager_start(void);