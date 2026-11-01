#include "device_telemetry.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "esp_log.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "wifi_manager.h"
#include "alert_manager.h"
#include "gnss_manager.h"
#include "mqtt_manager.h"
#include "command_processor.h"
#include "device_clock.h"

#define STATUS_PERIOD_US 10000000LL
#define TEST_COOLDOWN_US 5000000LL
static const char *TAG = "DEVICE_TELEMETRY";
static char s_device[49];
static bool s_started, s_serial;
static TaskHandle_t s_task;

static bool valid_device(const char *id)
{
    if (id == NULL || id[0] == '\0' || strnlen(id, 49) >= 49) return false;
    for (const char *p = id; *p; ++p)
        if (!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') ||
              (*p >= '0' && *p <= '9') || *p == '_' || *p == '-')) return false;
    return true;
}

/* Only validated identifiers and firmware constants enter quoted JSON strings.
 * No arbitrary serial input is ever included. All writes check truncation.
 */
static void utc_json(int64_t ms, char out[24])
{
    strcpy(out, "null");
    if (ms < 1577836800000LL || ms >= 4102444800000LL) return; /* 2020..2099 */
    time_t seconds = (time_t)(ms / 1000);
    struct tm utc;
    if (gmtime_r(&seconds, &utc) == NULL) return;
    strftime(out, 24, "\"%Y-%m-%dT%H:%M:%SZ\"", &utc);
}

static void observed_now(const gnss_snapshot_t *g, int64_t now, char out[24])
{
    strcpy(out, "null");
    int64_t clock_ms = device_clock_now_ms();
    if (clock_ms >= 0) { utc_json(clock_ms, out); return; }
    if (g == NULL || !g->has_current || !g->fix_valid ||
        g->source != GNSS_LOCATION_CURRENT) return;
    int64_t age = now - g->current_location.received_at_monotonic_us;
    if (age < 0 || age > 5000000LL) return;
    int64_t utc_ms = g->current_location.observed_at_utc_ms;
    if (utc_ms < 1577836800000LL || utc_ms >= 4102444800000LL) return;
    utc_json(utc_ms + age / 1000, out);
}

static size_t encode_status(const char *device, int buzzer, const gnss_snapshot_t *g,
                            int64_t now, char *out, size_t capacity)
{
    if (!valid_device(device)) return 0;
    char observed[24];
    observed_now(g, now, observed);
    const char *state = buzzer < 0 ? "null" : buzzer ? "\"BUZZER_ON\"" : "\"IDLE\"";
    int n = snprintf(out, capacity, "{\"schemaVersion\":1,\"deviceId\":\"%s\","
        "\"online\":true,\"mode\":\"REAL\",\"lteReady\":false,\"alertState\":%s,"
        "\"observedAt\":%s}", device, state, observed);
    return n > 0 && (size_t)n < capacity ? (size_t)n : 0;
}

static size_t append_command_ack(char *payload, size_t length, size_t capacity)
{
    char ack[512];
    size_t n = command_processor_ack_json(ack, sizeof(ack));
    if (!n) return length;
    if (length == 0) return 0;
    int written = snprintf(payload + length - 1, capacity - length + 1,
                           ",\"lastCommand\":%s}", ack);
    return written > 0 && (size_t)written < capacity - length + 1 ? length - 1 + (size_t)written : 0;
}

static size_t encode_event(const char *device, const char *id, const gnss_snapshot_t *g,
                           int64_t now, char *out, size_t capacity)
{
    char occurred[24], observed[24], position[160];
    observed_now(g, now, occurred);
    strcpy(position, "{\"type\":\"UNAVAILABLE\",\"lat\":null,\"lon\":null,\"observedAt\":null}");
    if (g != NULL && ((g->source == GNSS_LOCATION_CURRENT && g->has_current && g->fix_valid) ||
                     (g->source == GNSS_LOCATION_LAST_KNOWN && g->has_last_known))) {
        const gnss_location_t *p = &g->effective_location;
        if (isfinite(p->latitude_deg) && isfinite(p->longitude_deg) &&
            fabs(p->latitude_deg) <= 90 && fabs(p->longitude_deg) <= 180) {
            utc_json(p->observed_at_utc_ms, observed);
            snprintf(position, sizeof(position), "{\"type\":\"%s\",\"lat\":%.6f,\"lon\":%.6f,\"observedAt\":%s}",
                g->source == GNSS_LOCATION_CURRENT ? "CURRENT" : "LAST_KNOWN",
                p->latitude_deg, p->longitude_deg, observed);
        }
    }
    int n = snprintf(out, capacity, "{\"schemaVersion\":1,\"eventId\":\"%s\",\"deviceId\":\"%s\","
        "\"eventType\":\"TEST_ALERT\",\"isTest\":true,\"occurredAt\":%s,"
        "\"modelVersion\":\"firmware-test-v1\",\"confidence\":null,\"location\":%s}",
        id, device, occurred, position);
    return n > 0 && (size_t)n < capacity ? (size_t)n : 0;
}

static void new_event_id(char id[37])
{
    uint8_t bytes[16];
    esp_fill_random(bytes, sizeof(bytes)); /* Wi-Fi entropy active before acceptance. */
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    snprintf(id, 37, "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
        bytes[0],bytes[1],bytes[2],bytes[3],bytes[4],bytes[5],bytes[6],bytes[7],
        bytes[8],bytes[9],bytes[10],bytes[11],bytes[12],bytes[13],bytes[14],bytes[15]);
}

static void telemetry_worker(void *arg)
{
    (void)arg;
    char line[32] = {0}, pending[MQTT_MANAGER_MAX_PAYLOAD + 1U], event_id[37] = {0};
    size_t used = 0, pending_length = 0;
    bool invalid = false, pending_buzzer = false;
    uint32_t epoch = 0, pending_epoch = 0, seen_failures = 0;
    int previous_buzzer = -2, attempts = 0;
    int64_t next_status = 0, next_attempt = 0, next_ack = 0, last_test = -TEST_COOLDOWN_US;
    int64_t next_resources = 0, motor_off_at = 0;
    for (;;) {
        mqtt_manager_snapshot_t mqtt;
        mqtt_manager_get_snapshot(&mqtt);
        bool connected = mqtt.connected && mqtt.subscribed;
        int64_t now = esp_timer_get_time();
        if (motor_off_at && now >= motor_off_at) {
            vibration_off();
            motor_off_at = 0;
            ESP_LOGI(TAG, "MOTOR_TEST OFF requested; confirm physical vibration stopped");
        }
        if (now >= next_resources) {
            const unsigned caps = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;
            ESP_LOGI(TAG, "resources free_internal=%u min_internal=%u largest_internal=%u free_8bit=%u tasks=%u stack_min=%u",
                (unsigned)heap_caps_get_free_size(caps), (unsigned)heap_caps_get_minimum_free_size(caps),
                (unsigned)heap_caps_get_largest_free_block(caps), (unsigned)heap_caps_get_free_size(MALLOC_CAP_8BIT),
                (unsigned)uxTaskGetNumberOfTasks(), (unsigned)uxTaskGetStackHighWaterMark(NULL));
            next_resources = now + 10000000LL;
        }
        if (command_processor_enabled()) {
            device_clock_poll(connected);
            command_processor_tick(now);
            if (!command_processor_ack_pending()) {
                mqtt_manager_command_t frame;
                if (mqtt_manager_receive_command(&frame) == ESP_OK)
                    command_processor_process(&frame, connected ? mqtt.connection_epoch : 0, device_clock_now_ms());
            }
        }
        bool on = false;
        int buzzer = alert_manager_get_buzzer_state(&on) == ESP_OK ? (int)on : -1;
        if (connected && (epoch != mqtt.connection_epoch || now >= next_status || buzzer != previous_buzzer ||
                          (command_processor_ack_pending() && now >= next_ack))) {
            gnss_snapshot_t g = {0};
            if (gnss_manager_get_snapshot(&g) != ESP_OK) memset(&g, 0, sizeof(g));
            char payload[MQTT_MANAGER_MAX_PAYLOAD + 1U];
            size_t length = encode_status(s_device, buzzer, &g, now, payload, sizeof(payload));
            length = append_command_ack(payload, length, sizeof(payload));
            esp_err_t err = length ? mqtt_manager_publish(MQTT_CHANNEL_STATUS, payload, length) : ESP_FAIL;
            next_status = now + (err == ESP_OK ? STATUS_PERIOD_US : 1000000LL);
            next_ack = now + 1000000LL;
            if (err == ESP_OK) {
                if (command_processor_ack_pending()) {
                    command_processor_ack_queued();
                    ESP_LOGI(TAG, "command ACK status queued after processing (not broker delivery confirmation)");
                }
                epoch = mqtt.connection_epoch;
                previous_buzzer = buzzer;
                ESP_LOGI(TAG, "status queued: mode=REAL lteReady=false (not delivery confirmation)");
                ESP_LOGI(TAG, "worker stack minimum free=%u bytes", (unsigned)uxTaskGetStackHighWaterMark(NULL));
            } else {
                /* Avoid hot retry when the queue is full or state just changed. */
                epoch = mqtt.connection_epoch;
                previous_buzzer = buzzer;
                ESP_LOGW(TAG, "status queue failed: %d; retry in 1 s", (int)err);
            }
        }
        if (s_serial) {
            uint8_t bytes[32];
            int count = uart_read_bytes(UART_NUM_0, bytes, sizeof(bytes), 0);
            for (int i = 0; i < count; ++i) {
                unsigned char c = bytes[i];
                if (c == '\r' || c == '\n') {
                    line[used] = '\0';
                    if (!invalid && !strcmp(line, "TEST_WIFI_DROP") && command_processor_enabled()) {
                        esp_err_t err = wifi_manager_test_disconnect();
                        ESP_LOGI(TAG, "WIFI_DROP_TEST SDK disconnect result=%d; normal manager recovery required", (int)err);
                    }
                    if (!invalid && !strcmp(line, "TEST_MOTOR") && command_processor_enabled()) {
                        bool sounding = true;
                        if (now >= 10000000LL && !motor_off_at &&
                            alert_manager_get_buzzer_state(&sounding) == ESP_OK && !sounding) {
                            vibration_on();
                            motor_off_at = now + 500000LL;
                            ESP_LOGI(TAG, "MOTOR_TEST ON requested; duration=500ms; no alert/rescue");
                        } else ESP_LOGW(TAG, "MOTOR_TEST rejected: boot/buzzer/busy");
                    }
                    if (!invalid && !strcmp(line, "TEST_PUBLISH_OFFLINE") && !connected) {
                        gnss_snapshot_t g = {0};
                        char id[37], probe[MQTT_MANAGER_MAX_PAYLOAD + 1U];
                        new_event_id(id);
                        size_t n = encode_event(s_device, id, &g, now, probe, sizeof(probe));
                        esp_err_t err = n ? mqtt_manager_publish(MQTT_CHANNEL_EVENT, probe, n) : ESP_FAIL;
                        ESP_LOGI(TAG, "OFFLINE_PUBLISH_PROBE result=%d expected_offline_rejection=%d",
                                 (int)err, err == ESP_ERR_INVALID_STATE);
                    }
                    bool arm = strcmp(line, "TEST_ALERT_BUZZER") == 0 && command_processor_enabled();
                    if (!invalid && (strcmp(line, "TEST_ALERT") == 0 || arm)) {
                        if (connected && pending_length == 0 && now - last_test >= TEST_COOLDOWN_US && (!arm || !motor_off_at)) {
                            gnss_snapshot_t g = {0};
                            if (gnss_manager_get_snapshot(&g) != ESP_OK) memset(&g, 0, sizeof(g));
                            new_event_id(event_id);
                            pending_length = encode_event(s_device, event_id, &g, now, pending, sizeof(pending));
                            pending_epoch = mqtt.connection_epoch;
                            pending_buzzer = arm;
                            attempts = 0;
                            next_attempt = now;
                            last_test = now;
                            ESP_LOGI(TAG, "TEST_ALERT requested: eventId=%s isTest=true; local_buzzer_test=%d no rescue", event_id, (int)arm);
                        } else {
                            ESP_LOGW(TAG, "TEST_ALERT rejected: offline, pending or 5 s cooldown");
                        }
                    }
                    used = 0;
                    invalid = false;
                } else if (c < 32 || c > 126 || used >= sizeof(line) - 1) {
                    invalid = true;
                } else if (!invalid) {
                    line[used++] = (char)c;
                }
            }
        }
        if (pending_length) {
            if (!connected || mqtt.connection_epoch != pending_epoch) {
                pending_length = 0;
                ESP_LOGW(TAG, "TEST_ALERT cancelled before enqueue: connection changed; no automatic replay");
            } else if (now >= next_attempt) {
                esp_err_t err = mqtt_manager_publish(MQTT_CHANNEL_EVENT, pending, pending_length);
                ++attempts;
                if (err == ESP_OK) {
                    pending_length = 0;
                    if (pending_buzzer) {
                        esp_err_t arm_error = command_processor_arm_test(event_id, esp_timer_get_time());
                        ESP_LOGI(TAG, "local buzzer arm result=%d eventId=%s", (int)arm_error, event_id);
                    }
                    ESP_LOGI(TAG, "TEST_ALERT queued: eventId=%s (not delivery confirmation)", event_id);
                } else {
                    next_attempt = now + 1000000LL;
                    if (attempts >= 3) pending_length = 0;
                    ESP_LOGW(TAG, "TEST_ALERT queue failed: %d attempt=%d/3 eventId=%s", (int)err, attempts, event_id);
                }
            }
        }
        if (mqtt.publish_failures != seen_failures) {
            seen_failures = mqtt.publish_failures;
            ESP_LOGW(TAG, "transport publish failure count=%lu; queued events may be undelivered; inspect broker",
                     (unsigned long)seen_failures);
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

esp_err_t device_telemetry_start(const char *device_id, bool enable_serial_test)
{
    if (!valid_device(device_id)) return ESP_ERR_INVALID_ARG;
    if (s_started) return ESP_ERR_INVALID_STATE;
    if (enable_serial_test) {
#if CONFIG_ESP_CONSOLE_UART_NUM != 0
        return ESP_ERR_INVALID_STATE;
#else
        if (uart_is_driver_installed(UART_NUM_0)) return ESP_ERR_INVALID_STATE;
        esp_err_t err = uart_driver_install(UART_NUM_0, 256, 0, 0, NULL, 0);
        if (err != ESP_OK) return err;
#endif
    }
    strcpy(s_device, device_id);
    s_serial = enable_serial_test;
    if (xTaskCreatePinnedToCore(telemetry_worker, "device_telemetry", 8192, NULL, 2, &s_task, 0) != pdPASS) {
        if (enable_serial_test) uart_driver_delete(UART_NUM_0);
        return ESP_ERR_NO_MEM;
    }
    s_started = true;
    ESP_LOGI(TAG, "publisher started; serial TEST_ALERT=%s; no automatic test event",
             s_serial ? "ENABLED locally (UART0 115200)" : "disabled");
    return ESP_OK;
}
