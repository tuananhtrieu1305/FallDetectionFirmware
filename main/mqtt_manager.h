#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

#define MQTT_MANAGER_MAX_PAYLOAD 1024U
typedef enum {
    MQTT_MANAGER_DISABLED, MQTT_MANAGER_WAITING_WIFI, MQTT_MANAGER_CONNECTING,
    MQTT_MANAGER_CONNECTED, MQTT_MANAGER_ERROR,
} mqtt_manager_state_t;
typedef enum {
    MQTT_CHANNEL_STATUS, MQTT_CHANNEL_EVENT, MQTT_CHANNEL_LOCATION,
    MQTT_CHANNEL_HEALTH, MQTT_CHANNEL_COUNT,
} mqtt_manager_channel_t;
typedef struct {
    const char *broker_uri; /* Empty disables MQTT. mqtt:// or mqtts://host[:port]. */
    const char *device_id;  /* 1..48 ASCII letters/digits/_/-. */
    const char *username;   /* Optional; copied, never logged. */
    const char *password;   /* Optional; copied, never logged. */
    const char *server_certificate; /* mqtts requires CA PEM, valid for boot lifetime. */
} mqtt_manager_config_t;
typedef struct {
    mqtt_manager_state_t state;
    bool connected, subscribed;
    uint32_t connect_count, disconnect_count, connection_epoch;
    uint32_t rx_count, rx_dropped, tx_dropped;
    uint32_t publish_accepted, publish_failures, puback_count, error_count;
    esp_err_t last_error;
    int error_type, transport_errno;
} mqtt_manager_snapshot_t;
typedef struct {
    char payload[MQTT_MANAGER_MAX_PAYLOAD + 1U];
    size_t length;
    uint32_t connection_epoch; /* Not authorization or replay protection. */
    int message_id;
    bool duplicate;
} mqtt_manager_command_t;

/* Boot lifetime; call after Wi-Fi preparation, before acquisition. Allocates
 * bounded queues/client; worker waits for IPv4 before starting ESP-MQTT.
 * ESP_OK means accepted, not connected/subscribed. No command execution here.
 */
esp_err_t mqtt_manager_start(const mqtt_manager_config_t *config);
esp_err_t mqtt_manager_get_snapshot(mqtt_manager_snapshot_t *out);
/* Nonblocking copy to a four-entry queue. ESP_OK is NOT delivery confirmation.
 * Topic/QoS/retain selected from mqtt-v1, only status retained; max 1024 bytes.
 * Do not call this API from Sensor Task or an ISR.
 */
esp_err_t mqtt_manager_publish(mqtt_manager_channel_t channel, const char *payload, size_t length);
/* Nonblocking read for a future command worker. Raw bytes are NOT validated JSON,
 * authenticated commands or execution ACKs. Retained/wrong-topic/QoS frames drop.
 * Consumer must validate JSON/device/event/expiry/replay and connection_epoch.
 */
esp_err_t mqtt_manager_receive_command(mqtt_manager_command_t *out);
