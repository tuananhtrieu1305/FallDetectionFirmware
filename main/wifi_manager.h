#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
#include "esp_netif.h"

typedef enum {
    WIFI_MANAGER_DISABLED = 0,
    WIFI_MANAGER_STARTING,
    WIFI_MANAGER_CONNECTING,
    WIFI_MANAGER_WAITING_RETRY,
    WIFI_MANAGER_CONNECTED,
    WIFI_MANAGER_ERROR,
} wifi_manager_state_t;

typedef struct {
    const char *ssid;       /* 1..32 bytes; empty disables Wi-Fi. */
    const char *password;   /* WPA2/WPA3: 8..63 bytes, or 64 hexadecimal PSK bytes. */
} wifi_manager_config_t;

typedef struct {
    wifi_manager_state_t state;
    bool connected;        /* True only after this station obtains a nonzero IPv4. */
    esp_netif_ip_info_t ip_info;
    uint32_t connect_attempts;
    uint32_t disconnect_count;
    uint32_t retry_delay_ms;
    int64_t retry_at_us;    /* Monotonic; zero when no retry is pending. */
    uint16_t disconnect_reason;
    esp_err_t last_error;
} wifi_manager_snapshot_t;

/* Boot-lifetime owner of Wi-Fi STA. Call once BEFORE sensor acquisition starts.
 * Completes NVS/driver/PHY startup in the caller, then creates a worker for
 * association/DHCP/reconnect. Does NOT wait for an AP or DHCP. ESP_OK means
 * radio prepared and worker accepted, NOT connected: inspect snapshot.
 * Empty SSID: ESP_ERR_NOT_FOUND, no task/driver/NVS touched.
 * Init errors are returned and exposed as ERROR; no automatic NVS erase.
 * Runtime errors are exposed asynchronously. After init/runtime failure,
 * reboot is required; a task-allocation failure permits another start attempt.
 */
esp_err_t wifi_manager_start(const wifi_manager_config_t *config);

/* Thread-safe, short critical section; no network I/O or wait for connection. */
esp_err_t wifi_manager_get_snapshot(wifi_manager_snapshot_t *out);
bool wifi_manager_is_connected(void);

/* Local diagnostic fault injection, task context only. Uses normal SDK
 * disconnect event/backoff/DHCP recovery; does not reset or simulate an AP outage.
 */
esp_err_t wifi_manager_test_disconnect(void);
