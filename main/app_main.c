#include <inttypes.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_idf_version.h"

static const char *TAG = "fall_detection";

void app_main(void)
{
    esp_chip_info_t chip_info;
    uint32_t flash_size = 0;

    esp_chip_info(&chip_info);

    ESP_LOGI(TAG, "========================================");
    ESP_LOGI(TAG, "Fall Detection Firmware");
    ESP_LOGI(TAG, "Phase 0 hardware bring-up baseline");
    ESP_LOGI(TAG, "ESP-IDF: %s", esp_get_idf_version());
    ESP_LOGI(TAG, "Target: ESP32-S3");
    ESP_LOGI(TAG, "CPU cores: %d", chip_info.cores);
    ESP_LOGI(TAG, "Silicon revision: v%d.%d",
             chip_info.revision / 100,
             chip_info.revision % 100);

    if (esp_flash_get_size(NULL, &flash_size) == ESP_OK) {
        ESP_LOGI(TAG, "Flash size: %" PRIu32 " MB",
                 flash_size / (1024U * 1024U));
    } else {
        ESP_LOGE(TAG, "Failed to read flash size");
    }

    ESP_LOGI(TAG, "Free internal heap: %" PRIu32 " bytes",
             esp_get_free_heap_size());

    ESP_LOGI(TAG, "Baseline startup PASS");
    ESP_LOGI(TAG, "========================================");

    while (1) {
        ESP_LOGI(TAG, "Heartbeat: firmware running");
        vTaskDelay(pdMS_TO_TICKS(5000));
    }
}
