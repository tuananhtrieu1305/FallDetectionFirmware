#include "host_sdk.h"
#include <assert.h>
#include <stdio.h>
#include <stdarg.h>
#include "../../main/alert_manager.c"
static uint32_t duty;
static bool fail_set,fail_update,fail_get,stuck;
static unsigned stopped,delays;
esp_err_t ledc_set_duty(int mode,int channel,uint32_t n){(void)mode;(void)channel;if(fail_set)return ESP_FAIL;if(!stuck)duty=n;return ESP_OK;}
esp_err_t ledc_update_duty(int mode,int channel){(void)mode;(void)channel;return fail_update?ESP_FAIL:ESP_OK;}
uint32_t ledc_get_duty(int mode,int channel){(void)mode;(void)channel;return fail_get?LEDC_ERR_DUTY:duty;}
esp_err_t ledc_stop(int mode,int channel,int idle){(void)mode;(void)channel;assert(idle==0);++stopped;return ESP_OK;}
void vTaskDelay(TickType_t delay){assert(delay>0);++delays;}
void host_log(const char *fmt,...){(void)fmt;}
esp_err_t gpio_set_level(int p,int v){(void)p;(void)v;return ESP_OK;}
int gpio_get_level(int p){(void)p;return 0;}
esp_err_t gpio_config(const gpio_config_t *p){(void)p;return ESP_OK;}
esp_err_t ledc_timer_config(const ledc_timer_config_t *p){(void)p;return ESP_OK;}
esp_err_t ledc_channel_config(const ledc_channel_config_t *p){(void)p;return ESP_OK;}
const char *esp_err_to_name(esp_err_t e){(void)e;return "fake-sdk";}
int64_t esp_timer_get_time(void){return 0;}
void vTaskDelete(TaskHandle_t h){(void)h;}
BaseType_t xTaskCreate(TaskFunction_t f,const char *n,uint32_t s,void *a,unsigned p,TaskHandle_t *h){(void)f;(void)n;(void)s;(void)a;(void)p;(void)h;return pdPASS;}
int main(void){
 bool on;assert(alert_manager_get_buzzer_state(NULL)==ESP_ERR_INVALID_ARG);
 assert(buzzer_start_checked()==ESP_ERR_INVALID_STATE);assert(buzzer_stop_checked()==ESP_ERR_INVALID_STATE);
 assert(alert_manager_get_buzzer_state(&on)==ESP_ERR_INVALID_STATE);buzzer_initialized=true;
 assert(buzzer_start_checked()==ESP_OK&&duty==512);assert(buzzer_stop_checked()==ESP_OK&&duty==0&&delays==2);
 fail_set=true;duty=512;assert(buzzer_stop_checked()!=ESP_OK&&stopped==1);assert(buzzer_start_checked()!=ESP_OK);fail_set=false;
 fail_update=true;assert(buzzer_stop_checked()!=ESP_OK);fail_update=false;
 fail_get=true;assert(buzzer_stop_checked()!=ESP_OK);fail_get=false;
 duty=512;stuck=true;assert(buzzer_stop_checked()!=ESP_OK);duty=0;assert(buzzer_start_checked()!=ESP_OK);stuck=false;
 assert(buzzer_stop_checked()==ESP_OK);puts("checked buzzer APIs PASS: actual source, fake LEDC faults; no hardware claim");return 0;
}
