#include "sensor_bus.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

typedef struct {
    const i2c_master_bus_config_t *config;
    i2c_master_bus_handle_t *out;
    TaskHandle_t caller;
    esp_err_t result;
} bus_request_t;

static void allocate_bus(void *arg)
{
    bus_request_t *r = arg;
    r->result = i2c_new_master_bus(r->config, r->out);
    ESP_LOGI("SENSOR_BUS", "I2C IRQ allocated on core=%d result=%d", xPortGetCoreID(), (int)r->result);
    TaskHandle_t caller = r->caller;
    xTaskNotifyGive(caller);
    /* Request storage belongs to the waiting boot caller: never access it again. */
    vTaskDelete(NULL);
}

esp_err_t sensor_bus_create(const i2c_master_bus_config_t *config, i2c_master_bus_handle_t *out)
{
    if (config == NULL || out == NULL) return ESP_ERR_INVALID_ARG;
    bus_request_t request = {.config=config, .out=out, .caller=xTaskGetCurrentTaskHandle(), .result=ESP_FAIL};
    TaskHandle_t worker;
    if (xTaskCreatePinnedToCore(allocate_bus, "sensor_bus_boot", 4096, &request, 3, &worker, 1) != pdPASS)
        return ESP_ERR_NO_MEM;
    /* No timeout can leave a worker using a caller stack that has returned.
     * This is the same boot-only synchronous driver init as before; no sensor
     * timer exists yet, and this API must never be called from callbacks.
     */
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    return request.result;
}
