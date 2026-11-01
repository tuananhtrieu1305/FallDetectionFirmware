#pragma once
#include "../mqtt_manager/host_sdk.h"
void vTaskDelay(TickType_t);
unsigned uxTaskGetStackHighWaterMark(TaskHandle_t);
unsigned uxTaskGetNumberOfTasks(void);
#define MALLOC_CAP_8BIT 1U
#define MALLOC_CAP_INTERNAL 2U
size_t heap_caps_get_free_size(unsigned);
size_t heap_caps_get_minimum_free_size(unsigned);
size_t heap_caps_get_largest_free_block(unsigned);
void esp_fill_random(void *,size_t);
#define CONFIG_ESP_CONSOLE_UART_NUM 0
#define UART_NUM_0 0
bool uart_is_driver_installed(int);
esp_err_t uart_driver_install(int,int,int,int,void *,int);
esp_err_t uart_driver_delete(int);
int uart_read_bytes(int,void *,uint32_t,TickType_t);
