#include "device_clock.h"
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "esp_netif_sntp.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "gnss_manager.h"

static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static char s_server[254];
static bool s_initialized, s_started, s_synced;
static int64_t s_utc_ms, s_monotonic_us;

static void time_synced(struct timeval *tv)
{
    int64_t ms = (int64_t)tv->tv_sec * 1000 + tv->tv_usec / 1000;
    if (ms < 1577836800000LL || ms >= 4102444800000LL) return;
    int64_t now = esp_timer_get_time();
    portENTER_CRITICAL(&s_lock);
    s_utc_ms = ms;
    s_monotonic_us = now;
    s_synced = true;
    portEXIT_CRITICAL(&s_lock);
}

esp_err_t device_clock_init(const char *server)
{
    if (server == NULL || server[0] == 0 || strnlen(server, sizeof(s_server)) >= sizeof(s_server)) return ESP_ERR_INVALID_ARG;
    for (const char *p = server; *p; ++p)
        if (!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') ||
              (*p >= '0' && *p <= '9') || *p == '.' || *p == '-')) return ESP_ERR_INVALID_ARG;
    if (s_initialized) return ESP_ERR_INVALID_STATE;
    strcpy(s_server, server);
    esp_sntp_config_t config = ESP_NETIF_SNTP_DEFAULT_CONFIG(s_server);
    config.start = false;
    config.wait_for_sync = false;
    config.sync_cb = time_synced;
    esp_err_t err = esp_netif_sntp_init(&config);
    if (err == ESP_OK) s_initialized = true;
    return err;
}

void device_clock_poll(bool ready)
{
    if (s_initialized && !s_started && ready) {
        esp_err_t err = esp_netif_sntp_start();
        /* A failed start requires reboot; avoid a hot resource retry loop. */
        s_started = true;
        ESP_LOGI("DEVICE_CLOCK", "SNTP start result=%d; commands require actual UTC sync", (int)err);
    }
}

int64_t device_clock_now_ms(void)
{
    int64_t now = esp_timer_get_time();
    portENTER_CRITICAL(&s_lock);
    bool valid = s_synced;
    int64_t age = now - s_monotonic_us, utc = s_utc_ms;
    portEXIT_CRITICAL(&s_lock);
    if (valid && age >= 0 && age <= 3600000000LL) return utc + age / 1000;
    gnss_snapshot_t g;
    if (gnss_manager_get_snapshot(&g) == ESP_OK && g.has_current && g.fix_valid &&
        g.source == GNSS_LOCATION_CURRENT) {
        const gnss_location_t *p = &g.current_location;
        int64_t fix_age = now - p->received_at_monotonic_us;
        if (fix_age >= 0 && fix_age <= 5000000LL &&
            p->observed_at_utc_ms >= 1577836800000LL && p->observed_at_utc_ms < 4102444800000LL)
            return p->observed_at_utc_ms + fix_age / 1000;
    }
    return -1;
}
