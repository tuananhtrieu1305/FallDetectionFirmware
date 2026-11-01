#pragma once
#include "../mqtt_manager/host_sdk.h"
#include <sys/time.h>
typedef struct {
 bool start,wait_for_sync;
 void (*sync_cb)(struct timeval *);
 const char *server;
} esp_sntp_config_t;
#define ESP_NETIF_SNTP_DEFAULT_CONFIG(s) {.start=true,.wait_for_sync=true,.server=s}
esp_err_t esp_netif_sntp_init(const esp_sntp_config_t *);
esp_err_t esp_netif_sntp_start(void);
