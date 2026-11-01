#include "wifi_manager.h"

#include <inttypes.h>
#include <stddef.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "esp_wifi_default.h"
#include "nvs_flash.h"

#define WIFI_WORKER_STACK_BYTES 6144U
#define WIFI_WORKER_PRIORITY 3U
#define WIFI_WORKER_CORE 0
#define WIFI_RETRY_MIN_MS 1000U
#define WIFI_RETRY_MAX_MS 30000U
#define WIFI_CONNECT_TIMEOUT_US 30000000LL

static const char *TAG = "WIFI_MANAGER";
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static TaskHandle_t s_task;
static bool s_started;
static esp_netif_t *s_netif;
static bool s_driver_initialized;
static esp_event_handler_instance_t s_wifi_instance, s_ip_instance;
static wifi_config_t s_config;
static wifi_manager_snapshot_t s_status;
static struct {
    bool running;
    bool associated;
    bool stopped;
    uint32_t losses;
} s_observed;

static void clear_ip_locked(void)
{
    s_status.connected = false;
    memset(&s_status.ip_info, 0, sizeof(s_status.ip_info));
    s_status.state = WIFI_MANAGER_WAITING_RETRY;
}

/* Default event-loop context: bounded memory copies + notification only.
 * Boot caller owns radio preparation; worker owns runtime driver operations.
 */
static void wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    bool wake = true;
    portENTER_CRITICAL(&s_lock);
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        s_observed.running = true;
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_CONNECTED) {
        s_observed.associated = true;
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        s_observed.associated = false;
        ++s_observed.losses;
        clear_ip_locked();
        if (s_status.disconnect_count < UINT32_MAX) ++s_status.disconnect_count;
        if (data != NULL) {
            s_status.disconnect_reason = ((wifi_event_sta_disconnected_t *)data)->reason;
        }
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_STOP) {
        s_observed.running = false;
        s_observed.stopped = true;
        clear_ip_locked();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        const ip_event_got_ip_t *got = data;
        if (got != NULL && got->esp_netif == s_netif && got->ip_info.ip.addr != 0 &&
            s_observed.running && s_observed.associated) {
            s_status.ip_info = got->ip_info;
            s_status.connected = true;
            s_status.state = WIFI_MANAGER_CONNECTED;
            s_status.last_error = ESP_OK;
            s_status.retry_delay_ms = 0;
            s_status.retry_at_us = 0;
        }
    } else if (base == IP_EVENT && id == IP_EVENT_STA_LOST_IP) {
        ++s_observed.losses;
        clear_ip_locked();
    } else {
        wake = false;
    }
    TaskHandle_t task = s_task;
    portEXIT_CRITICAL(&s_lock);
    /* STA_START can arrive during synchronous radio preparation, before the
     * worker exists. Its observed state is retained for the worker's first pass.
     */
    if (wake && task != NULL) xTaskNotifyGive(task);
}

static void publish_retry(uint32_t delay_ms, int64_t at_us, esp_err_t error)
{
    uint16_t reason;
    portENTER_CRITICAL(&s_lock);
    if (!s_status.connected) {
        s_status.state = WIFI_MANAGER_WAITING_RETRY;
        s_status.retry_delay_ms = delay_ms;
        s_status.retry_at_us = at_us;
        s_status.last_error = error;
    }
    reason = s_status.disconnect_reason;
    portEXIT_CRITICAL(&s_lock);
    ESP_LOGW(TAG, "offline; retry in %" PRIu32 " ms; reason=%u error=%s",
             delay_ms, (unsigned)reason, esp_err_to_name(error));
}

static uint32_t increase_backoff(uint32_t delay_ms)
{
    return delay_ms < WIFI_RETRY_MAX_MS / 2U ? delay_ms * 2U : WIFI_RETRY_MAX_MS;
}

static TickType_t wait_until(int64_t deadline_us)
{
    int64_t remaining_us = deadline_us - esp_timer_get_time();
    if (remaining_us <= 0) return 1;
    uint32_t ms = (uint32_t)((remaining_us + 999LL) / 1000LL);
    TickType_t ticks = pdMS_TO_TICKS(ms);
    return ticks > 0 ? ticks : 1;
}

static void wifi_cleanup(esp_err_t error)
{
    /* Remove callbacks before releasing their resources/task. NVS, the default
     * event loop and the netif stack remain application-lifetime resources.
     */
    if (s_ip_instance != NULL) {
        esp_event_handler_instance_unregister(IP_EVENT, ESP_EVENT_ANY_ID, s_ip_instance);
        s_ip_instance = NULL;
    }
    if (s_wifi_instance != NULL) {
        esp_event_handler_instance_unregister(WIFI_EVENT, ESP_EVENT_ANY_ID, s_wifi_instance);
        s_wifi_instance = NULL;
    }
    if (s_driver_initialized) {
        esp_wifi_stop();
        esp_wifi_deinit();
        s_driver_initialized = false;
    }
    if (s_netif != NULL) {
        esp_netif_destroy_default_wifi(s_netif);
        s_netif = NULL;
    }
    memset(&s_config, 0, sizeof(s_config));
    portENTER_CRITICAL(&s_lock);
    clear_ip_locked();
    s_status.state = WIFI_MANAGER_ERROR;
    s_status.last_error = error;
    s_status.retry_delay_ms = 0;
    s_status.retry_at_us = 0;
    s_task = NULL;
    portEXIT_CRITICAL(&s_lock);
}

/* Boot-only preparation. Finish driver/PHY/NVS work before starting acquisition.
 * Association, DHCP and all later reconnects remain in the worker.
 */
static esp_err_t initialize_radio(void)
{
    esp_err_t err = nvs_flash_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "NVS init failed; existing NVS preserved (no automatic erase)");
        goto failed;
    }
    err = esp_netif_init();
    if (err != ESP_OK) goto failed;
    err = esp_event_loop_create_default();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) goto failed;
    /* The convenience create_default_wifi_sta() aborts on allocation/attach
     * failures in IDF 5.5.5. Use its checked steps to preserve sensor uptime.
     */
    esp_netif_config_t netif_config = ESP_NETIF_DEFAULT_WIFI_STA();
    s_netif = esp_netif_new(&netif_config);
    if (s_netif == NULL) { err = ESP_ERR_NO_MEM; goto failed; }
    err = esp_netif_attach_wifi_station(s_netif);
    if (err != ESP_OK) goto failed;
    err = esp_wifi_set_default_wifi_sta_handlers();
    if (err != ESP_OK) goto failed;
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    err = esp_wifi_init(&init);
    if (err != ESP_OK) goto failed;
    s_driver_initialized = true;
    err = esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                              wifi_event, NULL, &s_wifi_instance);
    if (err != ESP_OK) goto failed;
    err = esp_event_handler_instance_register(IP_EVENT, ESP_EVENT_ANY_ID,
                                              wifi_event, NULL, &s_ip_instance);
    if (err != ESP_OK) goto failed;
    /* Prevent station credentials being persisted to NVS by the Wi-Fi driver. */
    err = esp_wifi_set_storage(WIFI_STORAGE_RAM);
    if (err != ESP_OK) goto failed;
    err = esp_wifi_set_mode(WIFI_MODE_STA);
    if (err != ESP_OK) goto failed;
    err = esp_wifi_set_config(WIFI_IF_STA, &s_config);
    if (err != ESP_OK) goto failed;
    memset(&s_config, 0, sizeof(s_config));
    /* Demo sampling profile: keep the modem awake to avoid power-save wakeup
     * latency while acquiring at 100 Hz. This increases radio power consumption;
     * a battery profile needs its own timing/power validation.
     */
    err = esp_wifi_set_ps(WIFI_PS_NONE);
    if (err != ESP_OK) goto failed;
    err = esp_wifi_start();
    if (err != ESP_OK) goto failed;
    ESP_LOGI(TAG, "station started; awaiting IPv4 (2.4 GHz, WPA2/WPA3, DHCP)");
    return ESP_OK;

failed:
    wifi_cleanup(err);
    return err;
}

static void wifi_worker(void *arg)
{
    (void)arg;
    esp_err_t err = ESP_OK;

    bool connecting = false, retry_pending = false, was_online = false;
    uint32_t seen_losses = 0, next_backoff_ms = WIFI_RETRY_MIN_MS;
    int64_t retry_at_us = 0;
    int64_t connect_deadline_us = esp_timer_get_time() + WIFI_CONNECT_TIMEOUT_US;
    for (;;) {
        wifi_manager_snapshot_t status;
        bool running, associated, stopped;
        uint32_t losses;
        portENTER_CRITICAL(&s_lock);
        status = s_status;
        running = s_observed.running;
        associated = s_observed.associated;
        stopped = s_observed.stopped;
        losses = s_observed.losses;
        portEXIT_CRITICAL(&s_lock);
        int64_t now_us = esp_timer_get_time();
        if (stopped) { err = ESP_ERR_INVALID_STATE; goto failed; }
        if (!running && now_us >= connect_deadline_us) {
            err = ESP_ERR_TIMEOUT;
            goto failed;
        }
        if (status.connected) {
            if (!was_online) {
                ESP_LOGI(TAG, "GOT_IP " IPSTR "; connected=true attempts=%" PRIu32,
                         IP2STR(&status.ip_info.ip), status.connect_attempts);
            }
            was_online = true;
            connecting = false;
            retry_pending = false;
            next_backoff_ms = WIFI_RETRY_MIN_MS;
            seen_losses = losses;
        } else {
            was_online = false;
            bool lost = losses != seen_losses;
            bool timed_out = connecting && now_us >= connect_deadline_us;
            if (lost || timed_out) {
                seen_losses = losses;
                connecting = false;
                /* Reset an association whose DHCP lease was lost or timed out. */
                if (associated || timed_out) {
                    esp_err_t disconnect_err = esp_wifi_disconnect();
                    if (disconnect_err != ESP_OK && disconnect_err != ESP_ERR_WIFI_NOT_CONNECT) {
                        ESP_LOGW(TAG, "disconnect reset failed: %s", esp_err_to_name(disconnect_err));
                    }
                }
                if (!retry_pending) {
                    retry_at_us = now_us + (int64_t)next_backoff_ms * 1000;
                    publish_retry(next_backoff_ms, retry_at_us, timed_out ? ESP_ERR_TIMEOUT : ESP_OK);
                    next_backoff_ms = increase_backoff(next_backoff_ms);
                    retry_pending = true;
                }
            }
            if (!connecting && !retry_pending && running) {
                retry_pending = true; /* Initial attempt, no backoff needed. */
                retry_at_us = now_us;
            }
            if (retry_pending && running && now_us >= retry_at_us) {
                bool already_online;
                portENTER_CRITICAL(&s_lock);
                already_online = s_status.connected;
                if (!already_online) {
                    s_status.state = WIFI_MANAGER_CONNECTING;
                    s_status.retry_delay_ms = 0;
                    s_status.retry_at_us = 0;
                    if (s_status.connect_attempts < UINT32_MAX) ++s_status.connect_attempts;
                }
                portEXIT_CRITICAL(&s_lock);
                if (already_online) continue;
                retry_pending = false;
                connecting = true;
                connect_deadline_us = now_us + WIFI_CONNECT_TIMEOUT_US;
                err = esp_wifi_connect();
                if (err != ESP_OK) {
                    connecting = false;
                    retry_at_us = esp_timer_get_time() + (int64_t)next_backoff_ms * 1000;
                    publish_retry(next_backoff_ms, retry_at_us, err);
                    next_backoff_ms = increase_backoff(next_backoff_ms);
                    retry_pending = true;
                }
            }
        }
        TickType_t wait = portMAX_DELAY;
        if (retry_pending) wait = wait_until(retry_at_us);
        else if (connecting || !running) wait = wait_until(connect_deadline_us);
        ulTaskNotifyTake(pdTRUE, wait);
    }

failed:
    wifi_cleanup(err);
    ESP_LOGE(TAG, "worker stopped: %s; sensor tasks continue; reboot after fixing configuration",
             esp_err_to_name(err));
    vTaskDelete(NULL);
}

esp_err_t wifi_manager_start(const wifi_manager_config_t *config)
{
    if (config == NULL || config->ssid == NULL || config->password == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    size_t ssid_len = strnlen(config->ssid, sizeof(s_config.sta.ssid) + 1U);
    if (ssid_len == 0) return ESP_ERR_NOT_FOUND;
    size_t pass_len = strnlen(config->password, sizeof(s_config.sta.password) + 1U);
    if (ssid_len > sizeof(s_config.sta.ssid) || pass_len < 8 || pass_len > 64) {
        return ESP_ERR_INVALID_ARG;
    }
    if (pass_len == 64) {
        for (size_t i = 0; i < pass_len; ++i) {
            char c = config->password[i];
            if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'))) {
                return ESP_ERR_INVALID_ARG;
            }
        }
    }
    portENTER_CRITICAL(&s_lock);
    if (s_started) {
        portEXIT_CRITICAL(&s_lock);
        return ESP_ERR_INVALID_STATE;
    }
    s_started = true;
    s_status.state = WIFI_MANAGER_STARTING;
    s_status.last_error = ESP_OK;
    memset(&s_observed, 0, sizeof(s_observed));
    portEXIT_CRITICAL(&s_lock);
    memset(&s_config, 0, sizeof(s_config));
    memcpy(s_config.sta.ssid, config->ssid, ssid_len);
    memcpy(s_config.sta.password, config->password, pass_len);
    s_config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    s_config.sta.sae_pwe_h2e = WPA3_SAE_PWE_BOTH;
    s_config.sta.pmf_cfg.capable = true;
    esp_err_t err = initialize_radio();
    if (err != ESP_OK) return err;
    if (xTaskCreatePinnedToCore(wifi_worker, "wifi_manager", WIFI_WORKER_STACK_BYTES,
                    NULL, WIFI_WORKER_PRIORITY, &s_task, WIFI_WORKER_CORE) != pdPASS) {
        wifi_cleanup(ESP_ERR_NO_MEM);
        portENTER_CRITICAL(&s_lock);
        s_started = false;
        portEXIT_CRITICAL(&s_lock);
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}

esp_err_t wifi_manager_get_snapshot(wifi_manager_snapshot_t *out)
{
    if (out == NULL) return ESP_ERR_INVALID_ARG;
    portENTER_CRITICAL(&s_lock);
    *out = s_status;
    portEXIT_CRITICAL(&s_lock);
    return ESP_OK;
}

bool wifi_manager_is_connected(void)
{
    portENTER_CRITICAL(&s_lock);
    bool connected = s_status.connected;
    portEXIT_CRITICAL(&s_lock);
    return connected;
}

esp_err_t wifi_manager_test_disconnect(void)
{
    if (!wifi_manager_is_connected()) return ESP_ERR_INVALID_STATE;
    return esp_wifi_disconnect();
}
