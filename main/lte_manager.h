#pragma once

#include "esp_err.h"

// Phase 11.11: UART and ADC are mutually exclusive. Both 0 selects old 7.12e.
#define LTE_UART_AT_DIAG 0
#define LTE_TX_ADC_DIAG 0
#define LTE_UART_AT_DIAG_SKIP_WIFI 1

#if LTE_UART_AT_DIAG && LTE_TX_ADC_DIAG
#error "Select only one LTE diagnostic owner of GPIO18"
#endif

#define LTE_DIAG_SKIP_WIFI (LTE_TX_ADC_DIAG || \
                           (LTE_UART_AT_DIAG && LTE_UART_AT_DIAG_SKIP_WIFI))

/* Start the selected one-shot LTE diagnostic task. No LTE network workflow. */
esp_err_t lte_manager_start(void);
