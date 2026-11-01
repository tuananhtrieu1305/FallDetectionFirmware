/* Host-only ESP-IDF/FreeRTOS boundary. Never included by firmware builds. */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 0x101
#define ESP_ERR_INVALID_ARG 0x102
#define ESP_ERR_INVALID_STATE 0x103
#define ESP_ERR_NOT_FOUND 0x105
#define ESP_ERR_TIMEOUT 0x107
#define ESP_ERR_WIFI_NOT_CONNECT 0x300f
const char *esp_err_to_name(esp_err_t error);

typedef int BaseType_t;
typedef uint32_t TickType_t;
typedef void *TaskHandle_t;
typedef void (*TaskFunction_t)(void *);
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(lock) ((void)(lock))
#define portEXIT_CRITICAL(lock) ((void)(lock))
#define pdTRUE 1
#define pdPASS 1
#define pdMS_TO_TICKS(ms) ((TickType_t)((ms) / 10U))
#define portMAX_DELAY UINT32_MAX
BaseType_t xTaskCreate(TaskFunction_t fn, const char *name, uint32_t stack,
                       void *arg, unsigned priority, TaskHandle_t *handle);
BaseType_t xTaskCreatePinnedToCore(TaskFunction_t fn, const char *name, uint32_t stack,
                       void *arg, unsigned priority, TaskHandle_t *handle, int core);
uint32_t ulTaskNotifyTake(BaseType_t clear, TickType_t wait);
BaseType_t xTaskNotifyGive(TaskHandle_t task);
void vTaskDelete(TaskHandle_t task);
int64_t esp_timer_get_time(void);

typedef const char *esp_event_base_t;
extern const char host_wifi_event[], host_ip_event[];
#define WIFI_EVENT host_wifi_event
#define IP_EVENT host_ip_event
#define ESP_EVENT_ANY_ID -1
enum { WIFI_EVENT_STA_START, WIFI_EVENT_STA_CONNECTED,
       WIFI_EVENT_STA_DISCONNECTED, WIFI_EVENT_STA_STOP };
enum { IP_EVENT_STA_GOT_IP, IP_EVENT_STA_LOST_IP };
typedef void *esp_event_handler_instance_t;
typedef void (*esp_event_handler_t)(void *, esp_event_base_t, int32_t, void *);
esp_err_t esp_event_loop_create_default(void);
esp_err_t esp_event_handler_instance_register(esp_event_base_t base, int32_t id,
    esp_event_handler_t fn, void *arg, esp_event_handler_instance_t *instance);
esp_err_t esp_event_handler_instance_unregister(esp_event_base_t base, int32_t id,
    esp_event_handler_instance_t instance);

typedef struct { uint32_t addr; } esp_ip4_addr_t;
typedef struct { esp_ip4_addr_t ip, netmask, gw; } esp_netif_ip_info_t;
typedef struct { int dummy; } esp_netif_t;
typedef struct { esp_netif_t *esp_netif; esp_netif_ip_info_t ip_info;
                 bool ip_changed; } ip_event_got_ip_t;
typedef struct { uint16_t reason; } wifi_event_sta_disconnected_t;
esp_err_t esp_netif_init(void);
typedef struct { int dummy; } esp_netif_config_t;
#define ESP_NETIF_DEFAULT_WIFI_STA() ((esp_netif_config_t){0})
esp_netif_t *esp_netif_new(const esp_netif_config_t *config);
esp_err_t esp_netif_attach_wifi_station(esp_netif_t *netif);
esp_err_t esp_wifi_set_default_wifi_sta_handlers(void);
void esp_netif_destroy_default_wifi(void *netif);

typedef struct { int magic; } wifi_init_config_t;
#define WIFI_INIT_CONFIG_DEFAULT() ((wifi_init_config_t){ .magic = 1 })
enum { WIFI_STORAGE_RAM = 1, WIFI_MODE_STA = 1, WIFI_IF_STA = 0,
       WIFI_AUTH_WPA2_PSK = 3, WPA3_SAE_PWE_BOTH = 2 };
typedef struct {
    struct { uint8_t ssid[32], password[64];
             struct { int authmode; } threshold;
             int sae_pwe_h2e;
             struct { bool capable, required; } pmf_cfg;
             uint8_t failure_retry_cnt;
    } sta;
} wifi_config_t;
esp_err_t nvs_flash_init(void);
esp_err_t esp_wifi_init(const wifi_init_config_t *config);
esp_err_t esp_wifi_set_storage(int storage);
#define WIFI_PS_NONE 0
esp_err_t esp_wifi_set_ps(int mode);
esp_err_t esp_wifi_set_mode(int mode);
esp_err_t esp_wifi_set_config(int interface, wifi_config_t *config);
esp_err_t esp_wifi_start(void);
esp_err_t esp_wifi_connect(void);
esp_err_t esp_wifi_disconnect(void);
esp_err_t esp_wifi_stop(void);
esp_err_t esp_wifi_deinit(void);

#define IPSTR "%u.%u.%u.%u"
#define IP2STR(ip) ((unsigned)((ip)->addr & 255)), \
    ((unsigned)(((ip)->addr >> 8) & 255)), \
    ((unsigned)(((ip)->addr >> 16) & 255)), \
    ((unsigned)(((ip)->addr >> 24) & 255))
void host_log(const char *format, ...);
#define ESP_LOGI(tag, ...) ((void)(tag), host_log(__VA_ARGS__))
#define ESP_LOGW(tag, ...) ((void)(tag), host_log(__VA_ARGS__))
#define ESP_LOGE(tag, ...) ((void)(tag), host_log(__VA_ARGS__))
