/* Real manager, fake SDK/RTOS boundaries: never a hardware PASS. */
#include "host_sdk.h"
#include "mqtt_manager.h"
#include <assert.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct host_queue { unsigned size,count,head; char *data; };
static TaskFunction_t worker;
static esp_event_handler_t handler;
static bool callback_active,wifi=true,task_fail,init_fail,register_fail,start_fail;
static int queue_fail,queues,starts,subscriptions,enqueues,ticks;
static int subscribe_result=7,enqueue_result=9,grant=1;
static int64_t now_us;
static jmp_buf done;
static esp_mqtt_client_config_t installed;
static const char *scenario;
static const char *command_topic="iot/devices/waist-esp32s3-001/command";
static void emit(esp_mqtt_event_t e) { callback_active=true; handler(NULL,"MQTT",e.event_id,&e); callback_active=false; }
static void simple(int id) { emit((esp_mqtt_event_t){.event_id=id}); }
static void fragment(const char *topic,const char *data,int length,int total,int offset,bool retain) {
 emit((esp_mqtt_event_t){.event_id=MQTT_EVENT_DATA,.topic=(char *)topic,
  .topic_len=topic?(int)strlen(topic):0,.data=(char *)data,.data_len=length,
  .total_data_len=total,.current_data_offset=offset,.qos=1,.msg_id=42,.retain=retain});
}
static void hook(void) {
 if (ticks==3 && !strcmp(scenario,"wait-wifi")) { assert(!starts); wifi=true; }
 if (ticks==5) {
  if (!strcmp(scenario,"reconnect")) simple(MQTT_EVENT_DISCONNECTED);
  if (!strcmp(scenario,"fragment") || !strcmp(scenario,"queue-full")) {
   fragment(command_topic,"{\"a",3,7,0,false);fragment(NULL,"\":1}",4,7,3,false);
   if (!strcmp(scenario,"queue-full")) for(int i=0;i<6;i++) fragment(command_topic,"{}",2,2,0,false);
  }
  if (!strcmp(scenario,"bad-fragments")) {
   fragment(command_topic,"x",1,1025,0,false);
   fragment("iot/devices/other/command","{}",2,2,0,false);
   fragment(command_topic,"{}",2,2,0,true);
   fragment(command_topic,"a",1,4,0,false);fragment(NULL,"bc",2,4,2,false);
   fragment(command_topic,"x",-1,2,0,false);
   fragment(command_topic,NULL,1,2,0,false);
   fragment(command_topic,"{}",2,2,0,false);
  }
  if (!strcmp(scenario,"max-frame-zero-first")) {
   static char payload[1024];memset(payload,'a',sizeof(payload));
   fragment(command_topic,NULL,0,1024,0,false);
   fragment(NULL,payload,512,1024,0,false);
   fragment(NULL,payload+512,512,1024,512,false);
  }
  if (!strcmp(scenario,"publish") || !strcmp(scenario,"publish-fail")) {
   assert(mqtt_manager_publish(MQTT_CHANNEL_STATUS,"{}",2)==ESP_OK);
   assert(mqtt_manager_publish(MQTT_CHANNEL_HEALTH,"{}",2)==ESP_OK);
  }
  if (!strcmp(scenario,"tx-full")) for(int i=0;i<8;i++) (void)mqtt_manager_publish(MQTT_CHANNEL_EVENT,"{}",2);
  if (!strcmp(scenario,"error")) {
   esp_mqtt_error_codes_t err={.error_type=2,.esp_transport_sock_errno=111};
   emit((esp_mqtt_event_t){.event_id=MQTT_EVENT_ERROR,.error_handle=&err});
  }
 }
 if(ticks==8 && !strcmp(scenario,"reconnect")) simple(MQTT_EVENT_CONNECTED);
 if(ticks==10 && !strcmp(scenario,"publish")) simple(MQTT_EVENT_PUBLISHED);
}
BaseType_t xTaskCreatePinnedToCore(TaskFunction_t fn,const char *name,uint32_t stack,void *arg,unsigned priority,TaskHandle_t *h,int core) {
 (void)name;(void)arg;assert(stack>=4096 && priority<12 && core==0);
 if(task_fail)return 0;
 worker=fn;*h=(void *)1;return pdPASS;
}
uint32_t ulTaskNotifyTake(BaseType_t clear,TickType_t wait) { (void)clear;assert(wait>0);now_us+=100000;ticks++;hook();if(ticks>=(!strcmp(scenario,"no-suback")?140:40))longjmp(done,1);return 0; }
BaseType_t xTaskNotifyGive(TaskHandle_t h) { assert(h);return pdPASS; }
void vTaskDelete(TaskHandle_t h) { (void)h;longjmp(done,1); }
QueueHandle_t xQueueCreate(unsigned n,unsigned size) {
 if(queue_fail && queues+1==queue_fail)return NULL;
 struct host_queue *q=calloc(1,sizeof(*q));q->data=calloc(n,size);q->size=size;queues++;return q;
}
BaseType_t xQueueSend(QueueHandle_t q,const void *p,TickType_t wait) { assert(wait==0);if(q->count==4)return 0;memcpy(q->data+((q->head+q->count)%4)*q->size,p,q->size);q->count++;return pdPASS; }
BaseType_t xQueueReceive(QueueHandle_t q,void *p,TickType_t wait) { assert(wait==0);if(!q->count)return 0;memcpy(p,q->data+q->head*q->size,q->size);q->head=(q->head+1)%4;q->count--;return pdPASS; }
void vQueueDelete(QueueHandle_t q) { free(q->data);free(q);queues--; }
unsigned uxQueueMessagesWaiting(QueueHandle_t q){assert(q);return q->count;}
unsigned uxTaskGetStackHighWaterMark(TaskHandle_t h){(void)h;return 4096;}
int esp_mqtt_client_get_outbox_size(esp_mqtt_client_handle_t c){assert(c);return 0;}
int64_t esp_timer_get_time(void) {return now_us;}
bool wifi_manager_is_connected(void) {return wifi;}
esp_mqtt_client_handle_t esp_mqtt_client_init(const esp_mqtt_client_config_t *c) {installed=*c;return init_fail?NULL:(void *)2;}
esp_err_t esp_mqtt_client_register_event(esp_mqtt_client_handle_t c,int id,esp_event_handler_t fn,void *arg) {(void)c;(void)id;(void)arg;handler=fn;return register_fail?ESP_FAIL:ESP_OK;}
esp_err_t esp_mqtt_client_unregister_event(esp_mqtt_client_handle_t c,int id,esp_event_handler_t fn) {(void)c;(void)id;(void)fn;handler=NULL;return ESP_OK;}
esp_err_t esp_mqtt_client_destroy(esp_mqtt_client_handle_t c) {(void)c;return ESP_OK;}
esp_err_t esp_mqtt_client_start(esp_mqtt_client_handle_t c) {(void)c;assert(!callback_active);starts++;if(start_fail)return ESP_FAIL;simple(MQTT_EVENT_CONNECTED);return ESP_OK;}
int esp_mqtt_client_subscribe_single(esp_mqtt_client_handle_t c,const char *topic,int qos) {
 (void)c;assert(!callback_active && !strcmp(topic,command_topic) && qos==1);subscriptions++;
 if(subscribe_result<0)return subscribe_result;
 if(strcmp(scenario,"no-suback")) {char value=(char)grant;emit((esp_mqtt_event_t){.event_id=MQTT_EVENT_SUBSCRIBED,.msg_id=subscribe_result,.data=&value,.data_len=1});}
 return subscribe_result;
}
int esp_mqtt_client_enqueue(esp_mqtt_client_handle_t c,const char *topic,const char *data,int len,int qos,int retain,bool store) {
 (void)c;assert(!callback_active && data && len>0 && store);
 assert((strstr(topic,"/status")!=NULL)==(retain!=0));assert(qos==(strstr(topic,"/health")?0:1));enqueues++;return enqueue_result;
}
void host_log(const char *format,...) {char text[512];va_list a;va_start(a,format);vsnprintf(text,sizeof(text),format,a);va_end(a);assert(!strstr(text,"private-password") && !strstr(text,"private-user"));}
int main(int argc,char **argv) {
 assert(argc==2);scenario=argv[1];
 mqtt_manager_config_t c={.broker_uri="mqtt://192.0.2.1:1883",.device_id="waist-esp32s3-001",.username="private-user",.password="private-password"};
 if(!strcmp(scenario,"invalid")) {
  assert(mqtt_manager_start(NULL)==ESP_ERR_INVALID_ARG);
  c.broker_uri="";assert(mqtt_manager_start(&c)==ESP_ERR_NOT_FOUND);
  c.broker_uri="mqtt://user:secret@host";assert(mqtt_manager_start(&c)==ESP_ERR_INVALID_ARG);
  c.broker_uri="http://host";assert(mqtt_manager_start(&c)==ESP_ERR_INVALID_ARG);
  c.broker_uri="mqtts://host";assert(mqtt_manager_start(&c)==ESP_ERR_INVALID_ARG);
  c.broker_uri="mqtt://host";c.device_id="bad/+#";assert(mqtt_manager_start(&c)==ESP_ERR_INVALID_ARG);return 0;
 }
 if(!strcmp(scenario,"queue1-fail"))queue_fail=1;
 if(!strcmp(scenario,"queue2-fail"))queue_fail=2;
 if(!strcmp(scenario,"task-fail"))task_fail=true;
 if(!strcmp(scenario,"init-fail"))init_fail=true;
 if(!strcmp(scenario,"register-fail"))register_fail=true;
 if(queue_fail||task_fail||init_fail||register_fail) {assert(mqtt_manager_start(&c)!=ESP_OK);assert(!queues && !worker);return 0;}
 if(!strcmp(scenario,"wait-wifi"))wifi=false;
 if(!strcmp(scenario,"start-fail"))start_fail=true;
 if(!strcmp(scenario,"subscribe-fail"))subscribe_result=-1;
 if(!strcmp(scenario,"suback-denied"))grant=0x80;
 if(!strcmp(scenario,"publish-fail"))enqueue_result=-2;
 if(!strcmp(scenario,"tls-config")) {c.broker_uri="mqtts://test.example:8883";c.server_certificate="public-test-ca";}
 assert(mqtt_manager_start(&c)==ESP_OK);
 assert(mqtt_manager_start(&c)==ESP_ERR_INVALID_STATE);
 assert(installed.outbox.limit==8192 && installed.session.keepalive==30);
 assert(installed.session.last_will.retain && strstr(installed.session.last_will.msg,"\"online\":false"));
 assert(strstr(installed.session.last_will.topic,"/status"));
 assert(mqtt_manager_publish(MQTT_CHANNEL_EVENT,"{}",2)==ESP_ERR_INVALID_STATE);
 assert(mqtt_manager_get_snapshot(NULL)==ESP_ERR_INVALID_ARG);
 assert(mqtt_manager_receive_command(NULL)==ESP_ERR_INVALID_ARG);
 if(setjmp(done)==0)worker(NULL);
 mqtt_manager_snapshot_t s;assert(mqtt_manager_get_snapshot(&s)==ESP_OK);
 if(start_fail)assert(s.state==MQTT_MANAGER_ERROR && !s.connected && handler==NULL);
 else if(!strcmp(scenario,"subscribe-fail")||!strcmp(scenario,"suback-denied")||!strcmp(scenario,"no-suback"))assert(!s.subscribed);
 else if(!strcmp(scenario,"error"))assert(s.error_count==1);
 else {assert(s.connected && s.subscribed);assert(subscriptions==(!strcmp(scenario,"reconnect")?2:1));}
 if(!strcmp(scenario,"fragment")||!strcmp(scenario,"queue-full")||!strcmp(scenario,"bad-fragments")) {
  mqtt_manager_command_t frame;assert(mqtt_manager_receive_command(&frame)==ESP_OK);
  assert(frame.length==(!strcmp(scenario,"bad-fragments")?2:7));
  assert(frame.payload[frame.length]=='\0');
  if(!strcmp(scenario,"queue-full"))assert(s.rx_dropped>=3);
  if(!strcmp(scenario,"bad-fragments"))assert(s.rx_dropped>=6);
 }
 if(!strcmp(scenario,"publish"))assert(enqueues==2 && s.publish_accepted==2 && s.puback_count==1);
 if(!strcmp(scenario,"publish-fail"))assert(s.publish_failures==2);
 if(!strcmp(scenario,"tx-full"))assert(s.tx_dropped==4);
 if(!strcmp(scenario,"subscribe-fail"))assert(subscriptions==3);
 if(!strcmp(scenario,"no-suback"))assert(subscriptions==1 && s.last_error!=ESP_OK);
 if(!strcmp(scenario,"max-frame-zero-first")) {
  mqtt_manager_command_t frame;assert(mqtt_manager_receive_command(&frame)==ESP_OK);
  assert(frame.length==1024 && frame.payload[0]=='a' && frame.payload[1023]=='a' && !frame.payload[1024]);
 }
 assert(mqtt_manager_publish(MQTT_CHANNEL_COUNT,"{}",2)==ESP_ERR_INVALID_ARG);
 assert(mqtt_manager_publish(MQTT_CHANNEL_STATUS,NULL,2)==ESP_ERR_INVALID_ARG);
 assert(mqtt_manager_publish(MQTT_CHANNEL_STATUS,"",0)==ESP_ERR_INVALID_SIZE);
 assert(mqtt_manager_publish(MQTT_CHANNEL_STATUS,"x",1025)==ESP_ERR_INVALID_SIZE);
 printf("PASS %s\n",scenario);return 0;
}
