/* Real publisher/encoder, fake SDK I/O. This is not hardware evidence. */
#include "host_sdk.h"
#include <assert.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static struct tm *host_gmtime_r(const time_t *value, struct tm *out) {
 return gmtime_s(out,value)==0?out:NULL;
}
#define gmtime_r host_gmtime_r
#include "../../main/device_telemetry.c"

static TaskFunction_t task;
static jmp_buf finished;
static int64_t clock_us;
static const char *scenario;
static bool ready = true, fail_task, fail_uart;
static unsigned step, events, statuses, failures, installs, deletes, random_calls;
static char event_ids[4][37];
static char retried_payload[1025];
static int buzzer;
static unsigned motor_on_calls,motor_off_calls;
static unsigned offline_probe_calls;
static gnss_snapshot_t location;
static mqtt_manager_snapshot_t network = {.connected=true,.subscribed=true,.connection_epoch=1};
bool command_processor_enabled(void){return !strcmp(scenario,"motor");}
bool command_processor_ack_pending(void){return false;}
void command_processor_ack_queued(void){}
size_t command_processor_ack_json(char *out,size_t cap){(void)out;(void)cap;return 0;}
void command_processor_tick(int64_t now){(void)now;}
void command_processor_process(const mqtt_manager_command_t *f,uint32_t e,int64_t u){(void)f;(void)e;(void)u;}
esp_err_t command_processor_arm_test(const char *id,int64_t now){(void)id;(void)now;return ESP_FAIL;}
void device_clock_poll(bool ready_arg){(void)ready_arg;}
int64_t device_clock_now_ms(void){return -1;}
esp_err_t mqtt_manager_receive_command(mqtt_manager_command_t *out){(void)out;return ESP_ERR_NOT_FOUND;}
static char input[160];
static size_t input_offset;
static void command(const char *s) { snprintf(input,sizeof(input),"%s",s);input_offset=0; }
BaseType_t xTaskCreatePinnedToCore(TaskFunction_t fn,const char *n,uint32_t stack,void *a,unsigned priority,TaskHandle_t *h,int core) {
 (void)n;(void)a;assert(stack>=6144 && priority<12 && core==0);if(fail_task)return 0;task=fn;*h=(void *)1;return pdPASS;
}
void vTaskDelay(TickType_t delay) {
 assert(delay>0);clock_us+=100000;++step;
 if(step==5 && !strcmp(scenario,"reconnect")) {ready=false;network.connected=false;}
 if(step==10 && !strcmp(scenario,"reconnect")) {ready=true;network.connected=true;++network.connection_epoch;}
 if(step==8 && !strcmp(scenario,"buzzer")) buzzer=1;
 if(step==15 && !strcmp(scenario,"buzzer")) buzzer=0;
 if(step==3 && (!strcmp(scenario,"event") || !strcmp(scenario,"retry") || !strcmp(scenario,"giveup") || !strcmp(scenario,"offline") || !strcmp(scenario,"epoch"))) command("TEST_ALERT\r\n");
 if(step==3 && !strcmp(scenario,"serial")) command("INVALID\nTEST_ALERT_MORE\nTEST_ALERT\nTEST_ALERT\n");
 if(step==65 && !strcmp(scenario,"serial")) command("TEST_ALERT\n");
 if(step==3 && !strcmp(scenario,"overflow")) command("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXTEST_ALERT\n");
 if(step==3 && !strcmp(scenario,"binary")) {memcpy(input,"TEST\001ALERT\n",12);input_offset=0;}
 if(step==3 && !strcmp(scenario,"offline-probe")) command("TEST_PUBLISH_OFFLINE\n");
 if(step==110 && !strcmp(scenario,"motor")) command("TEST_MOTOR\nTEST_ALERT_BUZZER\n");
 if(step==5 && !strcmp(scenario,"epoch")) ++network.connection_epoch;
 if(step>=130) longjmp(finished,1);
}
int64_t esp_timer_get_time(void) {return clock_us;}
unsigned uxTaskGetStackHighWaterMark(TaskHandle_t h){(void)h;return 4096;}
unsigned uxTaskGetNumberOfTasks(void){return 12;}
size_t heap_caps_get_free_size(unsigned caps){(void)caps;return 100000;}
size_t heap_caps_get_minimum_free_size(unsigned caps){(void)caps;return 90000;}
size_t heap_caps_get_largest_free_block(unsigned caps){(void)caps;return 60000;}
void vibration_on(void){++motor_on_calls;}
void vibration_off(void){++motor_off_calls;}
esp_err_t wifi_manager_test_disconnect(void){return ESP_OK;}
void esp_fill_random(void *out,size_t n) {memset(out,++random_calls,n);}
bool uart_is_driver_installed(int n) {(void)n;return !strcmp(scenario,"uart-owned");}
esp_err_t uart_driver_install(int n,int rx,int tx,int q,void *h,int f) {(void)q;(void)h;(void)f;assert(n==0&&rx==256&&tx==0);installs++;return fail_uart?ESP_FAIL:ESP_OK;}
esp_err_t uart_driver_delete(int n) {assert(n==0);deletes++;return ESP_OK;}
int uart_read_bytes(int n,void *out,uint32_t count,TickType_t wait) {
 assert(n==0 && count<=32 && wait==0);
 size_t len=strlen(input+input_offset);if(len>count)len=count;memcpy(out,input+input_offset,len);input_offset+=len;return (int)len;
}
esp_err_t alert_manager_get_buzzer_state(bool *on) {if(buzzer<0)return ESP_FAIL;*on=buzzer!=0;return ESP_OK;}
esp_err_t gnss_manager_get_snapshot(gnss_snapshot_t *out) {*out=location;return !strcmp(scenario,"gnss-error")?ESP_FAIL:ESP_OK;}
esp_err_t mqtt_manager_get_snapshot(mqtt_manager_snapshot_t *out) {*out=network;out->connected=out->subscribed=ready;return ESP_OK;}
esp_err_t mqtt_manager_publish(mqtt_manager_channel_t channel,const char *payload,size_t length) {
 assert(length==strlen(payload)&&length<=1024);
 if(!ready){++offline_probe_calls;return ESP_ERR_INVALID_STATE;}
 if(channel==MQTT_CHANNEL_EVENT) {
  if((!strcmp(scenario,"retry")&&failures<2)||!strcmp(scenario,"giveup")||!strcmp(scenario,"epoch")) {
   if(failures)assert(!strcmp(retried_payload,payload));else strcpy(retried_payload,payload);
   ++failures;return ESP_ERR_NO_MEM;
  }
  if(!strcmp(scenario,"retry"))assert(!strcmp(retried_payload,payload));
  assert(events<4);const char *id=strstr(payload,"\"eventId\":\"");assert(id);memcpy(event_ids[events],id+11,36);event_ids[events][36]=0;++events;
 } else {assert(channel==MQTT_CHANNEL_STATUS);++statuses;}
 printf("PAYLOAD %d %s\n",channel,payload);return ESP_OK;
}
void host_log(const char *fmt,...) {(void)fmt;}
int main(int argc,char **argv) {
 assert(argc==2);scenario=argv[1];
 if(!strcmp(scenario,"encoders")) {
  char out[1025],small[2];gnss_snapshot_t g={0};
  assert(encode_status("bad\"id",0,NULL,0,out,sizeof(out))==0);
  assert(encode_status("device",0,NULL,0,small,sizeof(small))==0);
  assert(encode_status("device",-1,NULL,0,out,sizeof(out))>0);puts(out);assert(strstr(out,"\"alertState\":null"));
  assert(encode_event("device","123e4567-e89b-42d3-a456-426614174000",NULL,0,out,sizeof(out))>0);puts(out);
  g.source=GNSS_LOCATION_CURRENT;g.fix_valid=g.has_current=true;
  g.current_location=g.effective_location=(gnss_location_t){.latitude_deg=21,.longitude_deg=105.8,.observed_at_utc_ms=1793444400000LL,.received_at_monotonic_us=1000000};
  assert(encode_event("device","123e4567-e89b-42d3-a456-426614174000",&g,2000000,out,sizeof(out))>0);puts(out);assert(strstr(out,"CURRENT"));assert(!strstr(out,"\"occurredAt\":null"));
  char utc[24];observed_now(&g,7000000,utc);assert(!strcmp(utc,"null"));
  observed_now(&g,0,utc);assert(!strcmp(utc,"null"));
  utc_json(0,utc);assert(!strcmp(utc,"null"));
  utc_json(4102444800000LL,utc);assert(!strcmp(utc,"null"));
  g.source=GNSS_LOCATION_LAST_KNOWN;g.fix_valid=g.has_current=false;g.has_last_known=true;
  assert(encode_event("device","123e4567-e89b-42d3-a456-426614174000",&g,2000000,out,sizeof(out))>0);puts(out);assert(strstr(out,"LAST_KNOWN")&&strstr(out,"\"occurredAt\":null"));
  g.effective_location.latitude_deg=1000;
  assert(encode_event("device","123e4567-e89b-42d3-a456-426614174000",&g,0,out,sizeof(out))>0);assert(strstr(out,"UNAVAILABLE"));
  return 0;
 }
 bool serial=strcmp(scenario,"status")&&strcmp(scenario,"reconnect")&&strcmp(scenario,"buzzer")&&strcmp(scenario,"gnss-error");
 if(!strcmp(scenario,"task-fail"))fail_task=true;
 if(!strcmp(scenario,"uart-fail"))fail_uart=true;
 assert(device_telemetry_start(NULL,serial)==ESP_ERR_INVALID_ARG);
 assert(device_telemetry_start("bad/id",serial)==ESP_ERR_INVALID_ARG);
 esp_err_t e=device_telemetry_start("waist-esp32s3-001",serial);
 if(fail_task||fail_uart||!strcmp(scenario,"uart-owned")) {assert(e!=ESP_OK);if(fail_task)assert(deletes==1);return 0;}
 assert(e==ESP_OK);assert(device_telemetry_start("device",false)==ESP_ERR_INVALID_STATE);
 if(!strcmp(scenario,"offline")||!strcmp(scenario,"offline-probe"))ready=false;
 if(!strcmp(scenario,"gnss-error"))buzzer=-1;
 if(!setjmp(finished))task(NULL);
 if(!strcmp(scenario,"event")||!strcmp(scenario,"retry"))assert(events==1);
 else if(!strcmp(scenario,"serial"))assert(events==2&&strcmp(event_ids[0],event_ids[1]));
 else assert(events==0);
 if(!strcmp(scenario,"retry"))assert(failures==2);
 if(!strcmp(scenario,"giveup"))assert(failures==3);
 if(!strcmp(scenario,"motor"))assert(motor_on_calls==1&&motor_off_calls==1);
 if(!strcmp(scenario,"offline-probe"))assert(offline_probe_calls==1);
 if(!strcmp(scenario,"reconnect"))assert(statuses==3);
 if(!serial)assert(installs==0);
 return 0;
}
