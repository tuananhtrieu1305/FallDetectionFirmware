
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <inttypes.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "driver/gpio.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "lte_manager.h"

#if LTE_UART_AT_DIAG
#include "driver/uart.h"
#include "lte_at_response.h"
#endif

#if LTE_TX_ADC_DIAG
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_wifi.h"
#endif

#define TEST_GPIO           GPIO_NUM_18
#define SAMPLE_COUNT        500
#define SAMPLE_DELAY_MS     10
#define TASK_STACK_SIZE     4096
#define TASK_PRIORITY       3

static const char *TAG = "LTE";
static bool s_started = false;

#if LTE_UART_AT_DIAG

#define LTE_UART UART_NUM_2
#define LTE_UART_TX_GPIO GPIO_NUM_17
#define LTE_UART_RX_GPIO GPIO_NUM_18
#define LTE_UART_BAUD 115200
#define LTE_BOOT_WAIT_US 10000000LL
#define LTE_AT_WINDOW_US 2000000LL
#define LTE_RX_LOG_LIMIT 256U
#define LTE_RX_WINDOW_LIMIT 32768U
#define LTE_AT_ATTEMPTS 5

static void log_uart_rx(const uint8_t *data, size_t size, const char *phase)
{
    static const char digits[] = "0123456789ABCDEF";
    for (size_t offset = 0; offset < size; offset += 32) {
        char ascii[129];
        char hex[97];
        size_t n = size - offset;
        if (n > 32) n = 32;
        size_t a = 0, h = 0;
        bool abnormal = false;
        for (size_t i = 0; i < n; ++i) {
            uint8_t c = data[offset + i];
            hex[h++] = digits[c >> 4];
            hex[h++] = digits[c & 15];
            hex[h++] = ' ';
            if (c >= 32 && c <= 126) {
                if (c == '\\') ascii[a++] = '\\';
                ascii[a++] = (char)c;
            } else {
                ascii[a++] = '\\';
                if (c == '\r' || c == '\n' || c == '\t') {
                    ascii[a++] = c == '\r' ? 'r' : c == '\n' ? 'n' : 't';
                } else {
                    abnormal = true;
                    ascii[a++] = 'x';
                    ascii[a++] = digits[c >> 4];
                    ascii[a++] = digits[c & 15];
                }
            }
        }
        ascii[a] = '\0';
        hex[h] = '\0';
        ESP_LOGI(TAG, "AT RX data=%s | phase=%s bytes=%u", ascii, phase, (unsigned)n);
        if (abnormal) ESP_LOGW(TAG, "AT RX HEX=%s | phase=%s", hex, phase);
    }
}

// Return 1 only for a complete OK line; 0=deadline, -1=read error, -2=flood.
// The same task owns all UART2 reads, including boot/drain/response phases.
static int uart_rx_window(int64_t deadline, const char *phase,
                          lte_at_response_t *parser)
{
    uint8_t buffer[64];
    size_t total = 0, logged = 0;
    int result = 0;
    while (esp_timer_get_time() < deadline) {
        int count = uart_read_bytes(LTE_UART, buffer, sizeof(buffer), pdMS_TO_TICKS(20));
        if (count < 0) {
            ESP_LOGE(TAG, "AT RX read failed | phase=%s", phase);
            result = -1;
            break;
        }
        if (!count) continue;
        total += (size_t)count;
        size_t show = LTE_RX_LOG_LIMIT - logged;
        if (show > (size_t)count) show = (size_t)count;
        log_uart_rx(buffer, show, phase);
        logged += show;
        bool ok = false;
        if (parser) {
            for (int i = 0; i < count; ++i) {
                ok |= lte_at_response_feed(parser, buffer[i]);
            }
        }
        if (ok) { result = 1; break; }
        if (total >= LTE_RX_WINDOW_LIMIT) {
            ESP_LOGE(TAG, "AT RX flood limit reached | phase=%s", phase);
            result = -2;
            break;
        }
    }
    ESP_LOGI(TAG, "AT RX summary phase=%s total=%u logged=%u suppressed=%u",
             phase, (unsigned)total, (unsigned)logged, (unsigned)(total - logged));
    return result;
}

static void test_task(void *arg)
{
    (void)arg;
    bool owned = false;
    bool passed = false;
    int attempts = 0;
    esp_err_t err = ESP_OK;
    const char *result = "INIT_FAIL";
    ESP_LOGI(TAG, "LTE_UART_AT_DIAG START | Phase 11.11 | at_us=%" PRId64,
             esp_timer_get_time());

    // Never steal or delete a UART driver installed by another module.
    if (uart_is_driver_installed(LTE_UART)) {
        err = ESP_ERR_INVALID_STATE;
        goto init_failed;
    }
    uart_config_t config = {
        .baud_rate = LTE_UART_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    err = uart_param_config(LTE_UART, &config);
    if (err != ESP_OK) goto init_failed;
    // Only this task writes, at most 5*3 bytes: finite TX ring cannot fill.
    err = uart_driver_install(LTE_UART, 4096, 256, 0, NULL, 0);
    if (err != ESP_OK) goto init_failed;
    owned = true;
    err = uart_set_pin(LTE_UART, LTE_UART_TX_GPIO, LTE_UART_RX_GPIO,
                       UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    if (err != ESP_OK) goto init_failed;
    err = gpio_set_pull_mode(LTE_UART_RX_GPIO, GPIO_FLOATING);
    if (err != ESP_OK) goto init_failed;
    ESP_LOGI(TAG, "UART2 INIT PASS | TX=GPIO17 RX=GPIO18 baud=115200 8N1 flow=NONE; "
             "RX pulls OFF; ADC/7.12e excluded");

    result = "IO_ERROR";
    // Ten seconds AFTER UART init is stronger than ten seconds after boot.
    // Boot bytes are logged but never supplied to the OK parser.
    if (uart_rx_window(esp_timer_get_time() + LTE_BOOT_WAIT_US, "BOOT", NULL) < 0) {
        goto cleanup;
    }
    if (uart_rx_window(esp_timer_get_time() + 200000LL, "DRAIN", NULL) < 0) {
        goto cleanup;
    }
    size_t stale = 0;
    err = uart_get_buffered_data_len(LTE_UART, &stale);
    if (err != ESP_OK) goto cleanup;
    ESP_LOGI(TAG, "RX stale cleanup: boot/drain logged above; final flush buffered=%u bytes",
             (unsigned)stale);
    err = uart_flush_input(LTE_UART);
    if (err != ESP_OK) goto cleanup;

    for (int attempt = 1; attempt <= LTE_AT_ATTEMPTS; ++attempt) {
        attempts = attempt;
        lte_at_response_t parser = {0};
        const char command[] = "AT\r";
        int64_t sent_at = esp_timer_get_time();
        ESP_LOGI(TAG, "AT TX attempt=%d data=AT\\r hex=41 54 0D at_us=%" PRId64,
                 attempt, sent_at);
        int sent = uart_write_bytes(LTE_UART, command, sizeof(command) - 1);
        if (sent != (int)(sizeof(command) - 1)) {
            ESP_LOGE(TAG, "AT TX short/error sent=%d expected=3", sent);
            goto cleanup;
        }
        err = uart_wait_tx_done(LTE_UART, pdMS_TO_TICKS(200));
        if (err != ESP_OK) goto cleanup;
        int rx = uart_rx_window(sent_at + LTE_AT_WINDOW_US, "RESPONSE", &parser);
        if (rx < 0) goto cleanup;
        if (rx == 1) {
            passed = true;
            result = "PASS";
            ESP_LOGI(TAG, "AT RESPONSE PASS | attempt=%d | complete OK line received", attempt);
            break;
        }
        ESP_LOGW(TAG, "AT RESPONSE TIMEOUT | attempt=%d | no complete OK line", attempt);
        // The 2s response window also spaces retries; there is no extra sleep.
    }
    if (!passed) result = "TIMEOUT";
    goto cleanup;

init_failed:
    ESP_LOGE(TAG, "UART2 INIT FAIL | error=%s", esp_err_to_name(err));
cleanup:
    if (err != ESP_OK) ESP_LOGE(TAG, "UART2 operation failed: %s", esp_err_to_name(err));
    if (owned) {
        esp_err_t delete_err = uart_driver_delete(LTE_UART);
        if (delete_err != ESP_OK) {
            ESP_LOGE(TAG, "UART2 cleanup failed: %s", esp_err_to_name(delete_err));
            result = "CLEANUP_FAIL";
        }
    }
    ESP_LOGI(TAG, "LTE_UART_AT_DIAG COMPLETE | result=%s attempts=%d | "
             "AT-only, not LTE network readiness", result, attempts);
    vTaskDelete(NULL);
}

#elif LTE_TX_ADC_DIAG

#define ADC_DIAG_WINDOW_US 5000000LL
#define ADC_DIAG_ATTEN ADC_ATTEN_DB_12
#define ADC_DIAG_RAW_NEAR_RAIL 4090

// Task-owned, fixed storage: do not put both 500-element arrays on its stack.
static int s_raw[SAMPLE_COUNT];
static int s_mv[SAMPLE_COUNT];

static int compare_int(const void *a, const void *b)
{
    int x = *(const int *)a;
    int y = *(const int *)b;
    return (x > y) - (x < y);
}

static double median(const int *sorted, int count)
{
    return count % 2 ? sorted[count / 2] :
        ((double)sorted[count / 2 - 1] + sorted[count / 2]) / 2.0;
}

static void test_task(void *arg)
{
    (void)arg;
    adc_oneshot_unit_handle_t adc = NULL;
    adc_cali_handle_t cali = NULL;
    adc_unit_t mapped_unit;
    adc_channel_t mapped_channel;
    esp_err_t err;
    bool completed = false;

    ESP_LOGI(TAG, "LTE_TX_ADC_DIAG: UART2 OFF, no AT; 7.12e excluded; "
             "GPIO18 ADC2_CHANNEL_7, both pulls OFF; wait 8s");
    vTaskDelay(pdMS_TO_TICKS(8000));

    // This diagnostic firmware never initializes Wi-Fi. Refuse to sample if
    // another caller initialized it, rather than silently racing ADC2/radio.
    wifi_mode_t mode;
    err = esp_wifi_get_mode(&mode);
    if (err != ESP_ERR_WIFI_NOT_INIT) {
        ESP_LOGE(TAG, "ADC2 Wi-Fi isolation failed: expected NOT_INIT, got %s; abort",
                 esp_err_to_name(err));
        goto cleanup;
    }
    err = adc_oneshot_io_to_channel(TEST_GPIO, &mapped_unit, &mapped_channel);
    if (err != ESP_OK || mapped_unit != ADC_UNIT_2 || mapped_channel != ADC_CHANNEL_7) {
        ESP_LOGE(TAG, "GPIO18 ADC mapping mismatch/error=%s; abort", esp_err_to_name(err));
        goto cleanup;
    }

    gpio_config_t pin = {
        .pin_bit_mask = 1ULL << TEST_GPIO,
        .mode = GPIO_MODE_DISABLE,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    err = gpio_config(&pin);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "GPIO18 no-pull analog setup failed: %s", esp_err_to_name(err));
        goto cleanup;
    }
    adc_oneshot_unit_init_cfg_t unit = {
        .unit_id = ADC_UNIT_2,
        .ulp_mode = ADC_ULP_MODE_DISABLE,
    };
    err = adc_oneshot_new_unit(&unit, &adc);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "ADC2 init failed: %s", esp_err_to_name(err));
        goto cleanup;
    }
    adc_oneshot_chan_cfg_t channel = {
        .atten = ADC_DIAG_ATTEN,
        .bitwidth = ADC_BITWIDTH_12,
    };
    err = adc_oneshot_config_channel(adc, ADC_CHANNEL_7, &channel);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "ADC2 channel config failed: %s", esp_err_to_name(err));
        goto cleanup;
    }

#if ADC_CALI_SCHEME_CURVE_FITTING_SUPPORTED
    adc_cali_curve_fitting_config_t calibration = {
        .unit_id = ADC_UNIT_2,
        .chan = ADC_CHANNEL_7,
        .atten = ADC_DIAG_ATTEN,
        .bitwidth = ADC_BITWIDTH_12,
    };
    err = adc_cali_create_scheme_curve_fitting(&calibration, &cali);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "CALIBRATION FAILED: %s; RAW ONLY, voltage/bands unavailable",
                 esp_err_to_name(err));
    } else {
        ESP_LOGI(TAG, "Calibration curve-fitting OK; attenuation=12dB bitwidth=12");
    }
#else
    ESP_LOGW(TAG, "CALIBRATION UNSUPPORTED: RAW ONLY, voltage/bands unavailable");
#endif

    int raw_count = 0;
    int mv_count = 0;
    int read_errors = 0;
    int cal_errors = 0;
    int near_rail = 0;
    int low_rail = 0;
    int attempts = 0;
    int bands[6] = {0};
    esp_err_t last_read_error = ESP_OK;
    esp_err_t last_cal_error = ESP_OK;
    int64_t start = esp_timer_get_time();
    ESP_LOGI(TAG, "ADC SAMPLE START: max=500, spacing=10ms, window=5s; Wi-Fi NOT_INIT");
    while (attempts < SAMPLE_COUNT && esp_timer_get_time() - start < ADC_DIAG_WINDOW_US) {
        int raw;
        ++attempts;
        err = adc_oneshot_read(adc, ADC_CHANNEL_7, &raw);
        if (err != ESP_OK) {
            ++read_errors;
            last_read_error = err;
        } else {
            s_raw[raw_count++] = raw;
            if (raw <= 5) {
                ++low_rail;
            }
            if (raw >= ADC_DIAG_RAW_NEAR_RAIL) {
                ++near_rail;
            } else if (cali) {
                int mv;
                err = adc_cali_raw_to_voltage(cali, raw, &mv);
                if (err != ESP_OK || mv < 0) {
                    ++cal_errors;
                    last_cal_error = err == ESP_OK ? ESP_ERR_INVALID_RESPONSE : err;
                } else {
                    s_mv[mv_count++] = mv;
                    int band = mv < 200 ? 0 : mv < 1000 ? 1 : mv < 1600 ? 2 :
                               mv < 2000 ? 3 : mv < 3000 ? 4 : 5;
                    ++bands[band];
                }
            }
        }
        // No per-sample logging or busy wait. Sensor priority/timing unchanged.
        vTaskDelay(pdMS_TO_TICKS(SAMPLE_DELAY_MS));
    }
    int64_t elapsed = esp_timer_get_time() - start;
    ESP_LOGI(TAG, "ADC SAMPLE END: elapsed_us=%" PRId64 " attempts=%d valid=%d "
             "read_errors=%d last_read_error=%s", elapsed, attempts, raw_count,
             read_errors, esp_err_to_name(last_read_error));
    if (raw_count) {
        qsort(s_raw, raw_count, sizeof(s_raw[0]), compare_int);
        ESP_LOGI(TAG, "RAW min=%d median=%.1f max=%d | near_upper_rail=%d/%d (%.1f%%) "
                 "raw>=4090 | near_zero=%d/%d raw<=5",
                 s_raw[0], median(s_raw, raw_count), s_raw[raw_count - 1],
                 near_rail, raw_count, 100.0 * near_rail / raw_count, low_rail, raw_count);
    } else {
        ESP_LOGE(TAG, "NO VALID ADC SAMPLES; no voltage conclusion");
    }
    if (near_rail) {
        ESP_LOGW(TAG, "ADC SATURATION/NEAR-RAIL: upper voltage unknown; "
                 "rail samples excluded from mV stats/bands; cannot infer exact voltage");
    }
    if (low_rail) {
        ESP_LOGW(TAG, "Near-zero raw samples: ADC floor limits low-voltage accuracy");
    }
    if (cal_errors) {
        ESP_LOGE(TAG, "CALIBRATION CONVERSION FAILED count=%d last=%s; "
                 "mV statistics/bands suppressed", cal_errors, esp_err_to_name(last_cal_error));
    } else if (cali && mv_count) {
        qsort(s_mv, mv_count, sizeof(s_mv[0]), compare_int);
        ESP_LOGI(TAG, "CALIBRATED ESTIMATE (unsaturated n=%d): "
                 "min=%dmV median=%.1fmV max=%dmV; not an exact electrical measurement",
                 mv_count, s_mv[0], median(s_mv, mv_count), s_mv[mv_count - 1]);
        static const char *labels[] = {
            "[0,200)", "[200,1000)", "[1000,1600)",
            "[1600,2000)", "[2000,3000)", "[3000,+inf)"
        };
        for (int i = 0; i < 6; ++i) {
            ESP_LOGI(TAG, "VOLTAGE BAND %smV count=%d/%d ratio=%.1f%% "
                     "(calibrated unsaturated samples only)",
                     labels[i], bands[i], mv_count, 100.0 * bands[i] / mv_count);
        }
    } else {
        ESP_LOGW(TAG, "Voltage min/median/max and voltage bands UNAVAILABLE; use RAW only");
    }
    completed = raw_count > 0;

cleanup:
#if ADC_CALI_SCHEME_CURVE_FITTING_SUPPORTED
    if (cali) {
        esp_err_t cleanup_err = adc_cali_delete_scheme_curve_fitting(cali);
        if (cleanup_err != ESP_OK) {
            ESP_LOGE(TAG, "Calibration cleanup failed: %s", esp_err_to_name(cleanup_err));
        }
    }
#endif
    if (adc) {
        esp_err_t cleanup_err = adc_oneshot_del_unit(adc);
        if (cleanup_err != ESP_OK) {
            ESP_LOGE(TAG, "ADC2 cleanup failed: %s", esp_err_to_name(cleanup_err));
        }
    }
    ESP_LOGI(TAG, "LTE_TX_ADC_DIAG COMPLETE: %s; UART2 OFF; no AT; no repeat; "
             "does not establish LTE readiness", completed ? "SAMPLED" : "ABORTED");
    vTaskDelete(NULL);
}

#else // Historical Phase 7.12e: neither UART nor ADC diagnostic selected.

typedef struct {
    int high;
    int low;
    int transitions;
} gpio_test_result_t;

static bool configure_input(bool pulldown)
{
    gpio_config_t cfg = {
        .pin_bit_mask = (1ULL << GPIO_NUM_18),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = pulldown
            ? GPIO_PULLDOWN_ENABLE
            : GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };

    return gpio_config(&cfg) == ESP_OK;
}

static gpio_test_result_t sample_gpio(void)
{
    gpio_test_result_t result = {0};

    int previous = -1;

    for (int i = 0; i < SAMPLE_COUNT; i++) {
        int level = gpio_get_level(TEST_GPIO);

        if (level == 1) {
            result.high++;
        } else {
            result.low++;
        }

        if (previous >= 0 && previous != level) {
            result.transitions++;
        }

        previous = level;

        vTaskDelay(pdMS_TO_TICKS(SAMPLE_DELAY_MS));
    }

    return result;
}

static void test_task(void *arg)
{
    (void)arg;

    ESP_LOGI(TAG, "================================");
    ESP_LOGI(TAG, "PHASE 7.12e - TX IDLE DIAGNOSTIC");
    ESP_LOGI(TAG, "A7670C TX -> ESP32 GPIO18");
    ESP_LOGI(TAG, "UART disabled, no AT commands");
    ESP_LOGI(TAG, "================================");

    if (!configure_input(false)) {
        ESP_LOGE(TAG, "GPIO18 config failed");
        vTaskDelete(NULL);
        return;
    }

    ESP_LOGI(TAG, "Wait 8 seconds");
    vTaskDelay(pdMS_TO_TICKS(8000));

    ESP_LOGI(TAG, "TEST 1: NO PULL");

    gpio_test_result_t floating = sample_gpio();

    ESP_LOGI(
        TAG,
        "NO_PULL HIGH=%d LOW=%d transitions=%d",
        floating.high,
        floating.low,
        floating.transitions
    );

    if (!configure_input(true)) {
        ESP_LOGE(TAG, "GPIO18 pulldown config failed");
        vTaskDelete(NULL);
        return;
    }

    vTaskDelay(pdMS_TO_TICKS(500));

    ESP_LOGI(TAG, "TEST 2: INTERNAL PULLDOWN");

    gpio_test_result_t pulled = sample_gpio();

    ESP_LOGI(
        TAG,
        "PULLDOWN HIGH=%d LOW=%d transitions=%d",
        pulled.high,
        pulled.low,
        pulled.transitions
    );

    ESP_LOGI(TAG, "================================");
    ESP_LOGI(TAG, "PHASE 7.12e TEST COMPLETE");
    ESP_LOGI(TAG, "================================");

    vTaskDelete(NULL);
}

#endif // Selected LTE diagnostic

esp_err_t lte_manager_start(void)
{
    if (s_started) {
        return ESP_ERR_INVALID_STATE;
    }

    if (xTaskCreate(
            test_task,
            "lte_tx_diag",
            TASK_STACK_SIZE,
            NULL,
            TASK_PRIORITY,
            NULL) != pdPASS) {
#if LTE_UART_AT_DIAG
        ESP_LOGE(TAG, "LTE_UART_AT_DIAG COMPLETE | result=TASK_CREATE_FAIL attempts=0");
#endif
        return ESP_ERR_NO_MEM;
    }

    s_started = true;
    return ESP_OK;
}
