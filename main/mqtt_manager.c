#include "mqtt_manager.h"
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "mqtt_client.h"
#include "wifi_manager.h"

#define QUEUE_DEPTH 4U
#define TOPIC_SIZE 96U
#define SUBACK_TIMEOUT_US 10000000LL
static const char *TAG = "MQTT_MANAGER";
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static bool s_started;
static TaskHandle_t s_task;
static esp_mqtt_client_handle_t s_client;
static QueueHandle_t s_rx, s_tx;
static mqtt_manager_snapshot_t s_status;
static char s_uri[256], s_device[49], s_username[65], s_password[129];
static char s_client_id[56], s_command_topic[TOPIC_SIZE];
static char s_topics[MQTT_CHANNEL_COUNT][TOPIC_SIZE], s_will[256];
static struct { int id; bool ok; uint32_t epoch; } s_suback;
static struct { bool active; size_t total; mqtt_manager_command_t frame; } s_assembly;
typedef struct {
    mqtt_manager_channel_t channel;
    uint32_t epoch;
    size_t length;
    char payload[MQTT_MANAGER_MAX_PAYLOAD + 1U];
} publish_item_t;

static void drop_rx(void)
{
    s_assembly.active = false;
    portENTER_CRITICAL(&s_lock);
    ++s_status.rx_dropped;
    portEXIT_CRITICAL(&s_lock);
}

/* Only this serialized ESP-MQTT callback owns assembly storage. All copies are
 * bounded and queue operations have zero timeout; never log payloads or touch
 * actuators, subscribe or send network data here.
 */
static void receive_fragment(const esp_mqtt_event_t *event)
{
    if (event->current_data_offset < 0 || event->total_data_len <= 0 ||
        event->total_data_len > (int)MQTT_MANAGER_MAX_PAYLOAD ||
        event->data_len < 0 || (event->data_len > 0 && event->data == NULL) ||
        event->topic_len < 0 || event->retain || event->qos != 1) {
        drop_rx();
        return;
    }
    if (event->current_data_offset == 0 && (event->topic_len > 0 || !s_assembly.active)) {
        if (s_assembly.active) drop_rx();
        s_assembly.active = false;
        if (event->topic == NULL || event->topic_len != (int)strlen(s_command_topic) ||
            memcmp(event->topic, s_command_topic, (size_t)event->topic_len) != 0) {
            drop_rx();
            return;
        }
        portENTER_CRITICAL(&s_lock);
        bool connected = s_status.connected;
        s_assembly.frame.connection_epoch = s_status.connection_epoch;
        portEXIT_CRITICAL(&s_lock);
        if (!connected) { drop_rx(); return; }
        s_assembly.active = true;
        s_assembly.total = (size_t)event->total_data_len;
        s_assembly.frame.length = 0;
        s_assembly.frame.message_id = event->msg_id;
        s_assembly.frame.duplicate = event->dup;
    }
    if (!s_assembly.active || (size_t)event->current_data_offset != s_assembly.frame.length ||
        (size_t)event->total_data_len != s_assembly.total ||
        (size_t)event->data_len > s_assembly.total - s_assembly.frame.length ||
        event->msg_id != s_assembly.frame.message_id ||
        (event->topic_len > 0 && (event->topic == NULL ||
          event->topic_len != (int)strlen(s_command_topic) ||
          memcmp(event->topic, s_command_topic, (size_t)event->topic_len) != 0))) {
        drop_rx();
        return;
    }
    if (event->data_len > 0)
        memcpy(s_assembly.frame.payload + s_assembly.frame.length, event->data, (size_t)event->data_len);
    s_assembly.frame.length += (size_t)event->data_len;
    if (s_assembly.frame.length == s_assembly.total) {
        s_assembly.frame.payload[s_assembly.total] = '\0';
        s_assembly.active = false;
        if (xQueueSend(s_rx, &s_assembly.frame, 0) != pdPASS) { drop_rx(); return; }
        portENTER_CRITICAL(&s_lock);
        ++s_status.rx_count;
        portEXIT_CRITICAL(&s_lock);
    }
}

static void mqtt_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    (void)base;
    const esp_mqtt_event_t *event = data;
    if (event == NULL) return;
    if (id == MQTT_EVENT_DATA) {
        receive_fragment(event);
    } else {
        portENTER_CRITICAL(&s_lock);
        if (id == MQTT_EVENT_CONNECTED) {
            s_status.connected = true;
            s_status.subscribed = false;
            s_status.state = MQTT_MANAGER_CONNECTING;
            ++s_status.connect_count;
            ++s_status.connection_epoch;
            s_status.last_error = ESP_OK;
            s_suback.id = -1;
            s_assembly.active = false;
        } else if (id == MQTT_EVENT_DISCONNECTED) {
            s_status.connected = s_status.subscribed = false;
            s_status.state = MQTT_MANAGER_CONNECTING;
            ++s_status.disconnect_count;
            s_assembly.active = false;
        } else if (id == MQTT_EVENT_SUBSCRIBED) {
            /* Cache ACK before matching: it may arrive before subscribe returns. */
            s_suback.id = event->msg_id;
            s_suback.epoch = s_status.connection_epoch;
            s_suback.ok = event->data != NULL && event->data_len == 1 &&
                          (unsigned char)event->data[0] == 1;
        } else if (id == MQTT_EVENT_PUBLISHED) {
            ++s_status.puback_count;
        } else if (id == MQTT_EVENT_ERROR) {
            s_status.connected = s_status.subscribed = false;
            s_status.state = MQTT_MANAGER_CONNECTING;
            s_assembly.active = false;
            ++s_status.error_count;
            s_status.last_error = ESP_FAIL;
            if (event->error_handle != NULL) {
                s_status.error_type = event->error_handle->error_type;
                s_status.transport_errno = event->error_handle->esp_transport_sock_errno;
            }
        }
        portEXIT_CRITICAL(&s_lock);
    }
    if (s_task != NULL) xTaskNotifyGive(s_task);
}

static void mqtt_worker(void *arg)
{
    (void)arg;
    bool client_started = false;
    uint32_t epoch = 0, seen_rx = 0, seen_drops = 0, seen_errors = 0, seen_disconnects = 0;
    int pending = -1, subscribe_attempts = 0;
    int64_t subscribe_at = 0, subscribe_deadline = 0, next_resources = 0;
    for (;;) {
        bool wifi = wifi_manager_is_connected();
        if (!client_started && wifi) {
            esp_err_t err = esp_mqtt_client_start(s_client);
            if (err != ESP_OK) {
                /* No callback may keep notifying a task after it is deleted. */
                esp_mqtt_client_unregister_event(s_client, ESP_EVENT_ANY_ID, mqtt_event);
                esp_mqtt_client_destroy(s_client);
                s_client = NULL;
                portENTER_CRITICAL(&s_lock);
                s_status.state = MQTT_MANAGER_ERROR;
                s_status.connected = s_status.subscribed = false;
                s_status.last_error = err;
                s_task = NULL;
                portEXIT_CRITICAL(&s_lock);
                ESP_LOGE(TAG, "client task start failed: %d; reboot required", (int)err);
                vTaskDelete(NULL);
                return; /* Queues retained for boot lifetime; no concurrent queue teardown. */
            }
            client_started = true;
        }
        mqtt_manager_snapshot_t status;
        mqtt_manager_get_snapshot(&status);
        int64_t now = esp_timer_get_time();
        if (status.connected && status.connection_epoch != epoch) {
            epoch = status.connection_epoch;
            pending = -1;
            subscribe_attempts = 0;
            subscribe_at = now;
            ESP_LOGI(TAG, "connected: client=%s session=%" PRIu32, s_client_id, epoch);
        }
        if (status.connected && !status.subscribed && pending == -1 &&
            subscribe_attempts < 3 && now >= subscribe_at) {
            ++subscribe_attempts;
            pending = esp_mqtt_client_subscribe_single(s_client, s_command_topic, 1);
            subscribe_deadline = now + SUBACK_TIMEOUT_US;
            if (pending < 0) {
                pending = -1;
                subscribe_at = now + 1000000LL;
                ESP_LOGW(TAG, "subscribe enqueue failed; attempt=%d", subscribe_attempts);
            }
        }
        if (status.connected && pending >= 0) {
            portENTER_CRITICAL(&s_lock);
            bool matched = s_suback.id == pending && s_suback.epoch == epoch;
            bool accepted = matched && s_suback.ok;
            if (matched || now >= subscribe_deadline) {
                s_status.subscribed = accepted;
                s_status.last_error = accepted ? ESP_OK : ESP_FAIL;
                if (accepted) s_status.state = MQTT_MANAGER_CONNECTED;
            }
            portEXIT_CRITICAL(&s_lock);
            if (matched || now >= subscribe_deadline) {
                if (accepted) ESP_LOGI(TAG, "SUBACK confirmed: topic=%s qos=1", s_command_topic);
                else ESP_LOGW(TAG, "subscription denied or timed out; reconnect/configuration required");
                pending = -2; /* Bound attempts/outbox; retry on next connection epoch. */
            }
        }
        if (status.disconnect_count != seen_disconnects) {
            seen_disconnects = status.disconnect_count;
            ESP_LOGW(TAG, "disconnected; ESP-MQTT retries every 5000 ms");
        }
        if (status.error_count != seen_errors) {
            seen_errors = status.error_count;
            ESP_LOGW(TAG, "transport/broker error: type=%d errno=%d count=%" PRIu32,
                     status.error_type, status.transport_errno, seen_errors);
        }
        if (status.rx_count != seen_rx || status.rx_dropped != seen_drops) {
            seen_rx = status.rx_count;
            seen_drops = status.rx_dropped;
            ESP_LOGI(TAG, "command frame queued: received=%" PRIu32
                     " dropped=%" PRIu32 "; phase3 transport only", seen_rx, status.rx_dropped);
        }
        publish_item_t item;
        if (xQueueReceive(s_tx, &item, 0) == pdPASS) {
            mqtt_manager_get_snapshot(&status);
            int message_id = -1;
            if (status.connected && status.subscribed && status.connection_epoch == item.epoch) {
                message_id = esp_mqtt_client_enqueue(s_client, s_topics[item.channel],
                    item.payload, (int)item.length, item.channel == MQTT_CHANNEL_HEALTH ? 0 : 1,
                    item.channel == MQTT_CHANNEL_STATUS, true);
            }
            portENTER_CRITICAL(&s_lock);
            if (message_id >= 0) ++s_status.publish_accepted;
            else ++s_status.publish_failures;
            portEXIT_CRITICAL(&s_lock);
        }
        if (now >= next_resources) {
            ESP_LOGI(TAG, "resources rx_queue=%u/4 tx_queue=%u/4 outbox_bytes=%d stack_min=%u pub_ok=%" PRIu32 " pub_fail=%" PRIu32 " tx_drop=%" PRIu32,
                (unsigned)uxQueueMessagesWaiting(s_rx), (unsigned)uxQueueMessagesWaiting(s_tx),
                esp_mqtt_client_get_outbox_size(s_client), (unsigned)uxTaskGetStackHighWaterMark(NULL),
                status.publish_accepted, status.publish_failures, status.tx_dropped);
            next_resources = now + 10000000LL;
        }
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(100));
    }
}

static void startup_cleanup(bool registered)
{
    if (s_client != NULL) {
        if (registered) esp_mqtt_client_unregister_event(s_client, ESP_EVENT_ANY_ID, mqtt_event);
        esp_mqtt_client_destroy(s_client);
        s_client = NULL;
    }
    if (s_rx != NULL) { vQueueDelete(s_rx); s_rx = NULL; }
    if (s_tx != NULL) { vQueueDelete(s_tx); s_tx = NULL; }
    memset(s_password, 0, sizeof(s_password));
    s_task = NULL;
    s_started = false;
    s_status.state = MQTT_MANAGER_ERROR;
}

esp_err_t mqtt_manager_start(const mqtt_manager_config_t *config)
{
    if (config == NULL || config->broker_uri == NULL || config->device_id == NULL) return ESP_ERR_INVALID_ARG;
    size_t uri_length = strnlen(config->broker_uri, sizeof(s_uri));
    if (uri_length == 0) return ESP_ERR_NOT_FOUND;
    bool tls = strncmp(config->broker_uri, "mqtts://", 8) == 0;
    size_t prefix = tls ? 8U : 7U;
    if ((!tls && strncmp(config->broker_uri, "mqtt://", 7) != 0) || uri_length <= prefix ||
        uri_length >= sizeof(s_uri) || strpbrk(config->broker_uri + prefix, "@/?# \t\r\n") != NULL ||
        (tls && (config->server_certificate == NULL || config->server_certificate[0] == '\0'))) return ESP_ERR_INVALID_ARG;
    size_t device_length = strnlen(config->device_id, sizeof(s_device));
    if (device_length == 0 || device_length >= sizeof(s_device)) return ESP_ERR_INVALID_ARG;
    for (size_t i = 0; i < device_length; ++i) {
        char c = config->device_id[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') || c == '-' || c == '_')) return ESP_ERR_INVALID_ARG;
    }
    const char *username = config->username != NULL ? config->username : "";
    const char *password = config->password != NULL ? config->password : "";
    if (strnlen(username, sizeof(s_username)) >= sizeof(s_username) ||
        strnlen(password, sizeof(s_password)) >= sizeof(s_password) ||
        (password[0] != '\0' && username[0] == '\0')) return ESP_ERR_INVALID_ARG;
    if (s_started) return ESP_ERR_INVALID_STATE;
    s_started = true;
    strcpy(s_uri, config->broker_uri);
    strcpy(s_device, config->device_id);
    strcpy(s_username, username);
    strcpy(s_password, password);
    snprintf(s_client_id, sizeof(s_client_id), "real-%s", s_device);
    snprintf(s_command_topic, sizeof(s_command_topic), "iot/devices/%s/command", s_device);
    const char *suffix[] = {"status", "event", "location", "health"};
    for (unsigned i = 0; i < MQTT_CHANNEL_COUNT; ++i)
        snprintf(s_topics[i], sizeof(s_topics[i]), "iot/devices/%s/%s", s_device, suffix[i]);
    /* Minimal offline envelope: do not claim an actuator state at disconnect. */
    snprintf(s_will, sizeof(s_will), "{\"schemaVersion\":1,\"deviceId\":\"%s\","
        "\"online\":false,\"mode\":\"REAL\",\"lteReady\":false}", s_device);
    s_rx = xQueueCreate(QUEUE_DEPTH, sizeof(mqtt_manager_command_t));
    s_tx = xQueueCreate(QUEUE_DEPTH, sizeof(publish_item_t));
    esp_err_t err = ESP_ERR_NO_MEM;
    bool registered = false;
    if (s_rx == NULL || s_tx == NULL) goto failed;
    const esp_mqtt_client_config_t client_config = {
        .broker.address.uri = s_uri,
        .broker.verification.certificate = tls ? config->server_certificate : NULL,
        .credentials.client_id = s_client_id,
        .credentials.username = s_username[0] ? s_username : NULL,
        .credentials.authentication.password = s_username[0] ? s_password : NULL,
        .session.last_will = {.topic = s_topics[MQTT_CHANNEL_STATUS], .msg = s_will,
                             .qos = 1, .retain = true},
        .session.keepalive = 30,
        .session.protocol_ver = MQTT_PROTOCOL_V_3_1_1,
        .session.disable_clean_session = false,
        .network.reconnect_timeout_ms = 5000,
        .network.timeout_ms = 5000,
        .network.disable_auto_reconnect = false,
        .task.priority = 3, .task.stack_size = 6144,
        .buffer.size = 512, .buffer.out_size = 1400,
        .outbox.limit = 8192,
    };
    s_client = esp_mqtt_client_init(&client_config);
    if (s_client == NULL) goto failed;
    err = esp_mqtt_client_register_event(s_client, ESP_EVENT_ANY_ID, mqtt_event, NULL);
    if (err != ESP_OK) goto failed;
    registered = true;
    s_status.state = MQTT_MANAGER_WAITING_WIFI;
    if (xTaskCreatePinnedToCore(mqtt_worker, "mqtt_manager", 6144, NULL, 3, &s_task, 0) != pdPASS) {
        err = ESP_ERR_NO_MEM;
        goto failed;
    }
    return ESP_OK;
failed:
    startup_cleanup(registered);
    s_status.last_error = err;
    return err;
}

esp_err_t mqtt_manager_get_snapshot(mqtt_manager_snapshot_t *out)
{
    if (out == NULL) return ESP_ERR_INVALID_ARG;
    portENTER_CRITICAL(&s_lock);
    *out = s_status;
    portEXIT_CRITICAL(&s_lock);
    if (s_started && out->state != MQTT_MANAGER_ERROR && !wifi_manager_is_connected()) {
        out->state = MQTT_MANAGER_WAITING_WIFI;
        out->connected = out->subscribed = false;
    }
    return ESP_OK;
}

esp_err_t mqtt_manager_publish(mqtt_manager_channel_t channel, const char *payload, size_t length)
{
    if ((unsigned)channel >= MQTT_CHANNEL_COUNT || payload == NULL) return ESP_ERR_INVALID_ARG;
    if (length == 0 || length > MQTT_MANAGER_MAX_PAYLOAD) return ESP_ERR_INVALID_SIZE;
    mqtt_manager_snapshot_t status;
    mqtt_manager_get_snapshot(&status);
    if (!status.connected || !status.subscribed) return ESP_ERR_INVALID_STATE;
    publish_item_t item = {.channel = channel, .epoch = status.connection_epoch, .length = length};
    memcpy(item.payload, payload, length);
    item.payload[length] = '\0';
    if (xQueueSend(s_tx, &item, 0) != pdPASS) {
        portENTER_CRITICAL(&s_lock);
        ++s_status.tx_dropped;
        portEXIT_CRITICAL(&s_lock);
        return ESP_ERR_NO_MEM;
    }
    xTaskNotifyGive(s_task);
    return ESP_OK;
}

esp_err_t mqtt_manager_receive_command(mqtt_manager_command_t *out)
{
    if (out == NULL) return ESP_ERR_INVALID_ARG;
    if (!s_started || s_rx == NULL) return ESP_ERR_INVALID_STATE;
    return xQueueReceive(s_rx, out, 0) == pdPASS ? ESP_OK : ESP_ERR_NOT_FOUND;
}
