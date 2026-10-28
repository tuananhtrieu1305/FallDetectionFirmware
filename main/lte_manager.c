
#include <stdbool.h>
#include <stdint.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "driver/gpio.h"
#include "esp_err.h"
#include "esp_log.h"

#include "lte_manager.h"

#define TEST_GPIO           GPIO_NUM_18
#define SAMPLE_COUNT        500
#define SAMPLE_DELAY_MS     10
#define TASK_STACK_SIZE     4096
#define TASK_PRIORITY       3

static const char *TAG = "LTE";
static bool s_started = false;

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
        return ESP_ERR_NO_MEM;
    }

    s_started = true;
    return ESP_OK;
}
