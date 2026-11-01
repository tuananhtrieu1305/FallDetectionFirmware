#pragma once
#include "../mqtt_manager/host_sdk.h"
enum {GPIO_NUM_4=4,GPIO_NUM_5,GPIO_NUM_6,GPIO_MODE_INPUT,GPIO_MODE_OUTPUT,
 GPIO_PULLUP_DISABLE,GPIO_PULLUP_ENABLE,GPIO_PULLDOWN_DISABLE,GPIO_PULLDOWN_ENABLE,
 GPIO_INTR_DISABLE,LEDC_LOW_SPEED_MODE,LEDC_TIMER_0,LEDC_CHANNEL_0,LEDC_TIMER_10_BIT,
 LEDC_AUTO_CLK,LEDC_INTR_DISABLE};
#define LEDC_ERR_DUTY UINT32_MAX
#define ESP_LOG_INFO 1
#define ESP_LOG_ERROR 2
#define ESP_LOG_LEVEL(level,tag,...) ((void)(level),(void)(tag),host_log(__VA_ARGS__))
typedef struct {uint64_t pin_bit_mask;int mode,pull_up_en,pull_down_en,intr_type;} gpio_config_t;
typedef struct {int speed_mode,duty_resolution,timer_num,freq_hz,clk_cfg;bool deconfigure;} ledc_timer_config_t;
typedef struct {int gpio_num,speed_mode,channel,intr_type,timer_sel;uint32_t duty,hpoint;struct {unsigned output_invert;} flags;} ledc_channel_config_t;
esp_err_t gpio_set_level(int,int);
int gpio_get_level(int);
esp_err_t gpio_config(const gpio_config_t *);
esp_err_t ledc_set_duty(int,int,uint32_t);
esp_err_t ledc_update_duty(int,int);
uint32_t ledc_get_duty(int,int);
esp_err_t ledc_stop(int,int,int);
esp_err_t ledc_timer_config(const ledc_timer_config_t *);
esp_err_t ledc_channel_config(const ledc_channel_config_t *);
const char *esp_err_to_name(esp_err_t);
void vTaskDelay(TickType_t);
BaseType_t xTaskCreate(TaskFunction_t,const char *,uint32_t,void *,unsigned,TaskHandle_t *);
