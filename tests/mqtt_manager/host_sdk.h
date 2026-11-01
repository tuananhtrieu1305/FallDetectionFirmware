#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef int esp_err_t;
typedef struct { struct { uint32_t addr; } ip,netmask,gw; } esp_netif_ip_info_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 0x101
#define ESP_ERR_INVALID_ARG 0x102
#define ESP_ERR_INVALID_STATE 0x103
#define ESP_ERR_INVALID_SIZE 0x104
#define ESP_ERR_NOT_FOUND 0x105
#define ESP_ERR_TIMEOUT 0x107
typedef uint32_t TickType_t;
typedef void *TaskHandle_t;
typedef void (*TaskFunction_t)(void *);
typedef int BaseType_t;
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(p) ((void)(p))
#define portEXIT_CRITICAL(p) ((void)(p))
#define pdTRUE 1
#define pdPASS 1
#define pdMS_TO_TICKS(ms) ((ms)/10U)
BaseType_t xTaskCreatePinnedToCore(TaskFunction_t,const char *,uint32_t,void *,unsigned,TaskHandle_t *,int);
uint32_t ulTaskNotifyTake(BaseType_t,TickType_t);
BaseType_t xTaskNotifyGive(TaskHandle_t);
void vTaskDelete(TaskHandle_t);
typedef struct host_queue *QueueHandle_t;
QueueHandle_t xQueueCreate(unsigned,unsigned);
BaseType_t xQueueSend(QueueHandle_t,const void *,TickType_t);
BaseType_t xQueueReceive(QueueHandle_t,void *,TickType_t);
void vQueueDelete(QueueHandle_t);
unsigned uxQueueMessagesWaiting(QueueHandle_t);
unsigned uxTaskGetStackHighWaterMark(TaskHandle_t);
int64_t esp_timer_get_time(void);
bool wifi_manager_is_connected(void);
typedef const char *esp_event_base_t;
typedef void (*esp_event_handler_t)(void *,esp_event_base_t,int32_t,void *);
typedef void *esp_mqtt_client_handle_t;
enum { MQTT_EVENT_CONNECTED=1,MQTT_EVENT_DISCONNECTED,MQTT_EVENT_SUBSCRIBED,
       MQTT_EVENT_PUBLISHED,MQTT_EVENT_DATA,MQTT_EVENT_ERROR,MQTT_EVENT_DELETED };
#define ESP_EVENT_ANY_ID -1
#define MQTT_PROTOCOL_V_3_1_1 4
typedef struct { int error_type,esp_transport_sock_errno; } esp_mqtt_error_codes_t;
typedef struct {
 int event_id,msg_id,data_len,total_data_len,current_data_offset,topic_len,qos;
 char *data,*topic;
 bool retain,dup;
 esp_mqtt_error_codes_t *error_handle;
 esp_mqtt_client_handle_t client;
} esp_mqtt_event_t;
typedef struct {
 struct { struct { const char *uri; } address;
          struct { const char *certificate; } verification; } broker;
 struct { const char *username,*client_id;
          struct { const char *password; } authentication; } credentials;
 struct { struct { const char *topic,*msg; int msg_len,qos,retain; } last_will;
          bool disable_clean_session; int keepalive,protocol_ver; } session;
 struct { int reconnect_timeout_ms,timeout_ms; bool disable_auto_reconnect; } network;
 struct { int priority,stack_size; } task;
 struct { int size,out_size; } buffer;
 struct { uint64_t limit; } outbox;
} esp_mqtt_client_config_t;
esp_mqtt_client_handle_t esp_mqtt_client_init(const esp_mqtt_client_config_t *);
esp_err_t esp_mqtt_client_register_event(esp_mqtt_client_handle_t,int,esp_event_handler_t,void *);
esp_err_t esp_mqtt_client_unregister_event(esp_mqtt_client_handle_t,int,esp_event_handler_t);
esp_err_t esp_mqtt_client_destroy(esp_mqtt_client_handle_t);
esp_err_t esp_mqtt_client_start(esp_mqtt_client_handle_t);
int esp_mqtt_client_subscribe_single(esp_mqtt_client_handle_t,const char *,int);
int esp_mqtt_client_enqueue(esp_mqtt_client_handle_t,const char *,const char *,int,int,int,bool);
int esp_mqtt_client_get_outbox_size(esp_mqtt_client_handle_t);
void host_log(const char *,...);
#define ESP_LOGI(tag,...) ((void)(tag),host_log(__VA_ARGS__))
#define ESP_LOGW(tag,...) ((void)(tag),host_log(__VA_ARGS__))
#define ESP_LOGE(tag,...) ((void)(tag),host_log(__VA_ARGS__))
