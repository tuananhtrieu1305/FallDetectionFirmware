#include "host_sdk.h"
#include "sensor_bus.h"
#include <assert.h>
#include <stdio.h>
static int core,allocations,notifications;
static bool fail_task,fail_driver;
int xPortGetCoreID(void){return core;}
TaskHandle_t xTaskGetCurrentTaskHandle(void){return (void *)1;}
BaseType_t xTaskCreatePinnedToCore(TaskFunction_t f,const char *n,uint32_t stack,void *arg,unsigned priority,TaskHandle_t *h,int c){(void)n;assert(stack>=3072&&priority<12&&c==1);if(fail_task)return 0;core=1;f(arg);core=0;*h=(void *)2;return pdPASS;}
BaseType_t xTaskNotifyGive(TaskHandle_t h){assert(h==(void *)1);notifications++;return pdPASS;}
uint32_t ulTaskNotifyTake(BaseType_t clear,TickType_t wait){assert(clear&&wait==portMAX_DELAY&&notifications==1);notifications=0;return 1;}
void vTaskDelete(TaskHandle_t h){assert(!h);}
esp_err_t i2c_new_master_bus(const i2c_master_bus_config_t *c,i2c_master_bus_handle_t *h){assert(core==1&&c);++allocations;*h=(void *)3;return fail_driver?ESP_FAIL:ESP_OK;}
void host_log(const char *f,...){(void)f;}
int main(void){i2c_master_bus_config_t c={0};i2c_master_bus_handle_t h=NULL;
 assert(sensor_bus_create(NULL,&h)==ESP_ERR_INVALID_ARG);assert(sensor_bus_create(&c,NULL)==ESP_ERR_INVALID_ARG);
 fail_task=true;assert(sensor_bus_create(&c,&h)==ESP_ERR_NO_MEM);assert(!allocations);fail_task=false;
 fail_driver=true;assert(sensor_bus_create(&c,&h)==ESP_FAIL);fail_driver=false;
 assert(sensor_bus_create(&c,&h)==ESP_OK&&h==(void *)3&&allocations==2&&!notifications);
 puts("I2C IRQ allocation core1, boot wait and error propagation PASS; fake driver");return 0;}
