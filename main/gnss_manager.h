#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"

typedef enum {
    GNSS_LOCATION_UNAVAILABLE = 0,
    GNSS_LOCATION_CURRENT,
    GNSS_LOCATION_LAST_KNOWN
} gnss_location_source_t;

typedef struct {
    double latitude_deg;
    double longitude_deg;

    uint8_t satellites_used;

    // GPS UTC time, Unix milliseconds
    int64_t observed_at_utc_ms;

    // ESP32 monotonic time, not UTC
    int64_t received_at_monotonic_us;
} gnss_location_t;

typedef struct {
    gnss_location_source_t source;

    // True only when current location is valid
    bool fix_valid;

    bool has_current;
    bool has_last_known;

    gnss_location_t current_location;
    gnss_location_t last_known_location;

    // Only use when source != UNAVAILABLE
    gnss_location_t effective_location;

    // UINT32_MAX when no location is available
    uint32_t location_age_ms;
} gnss_snapshot_t;

// Initialize UART1 and create GNSS task
esp_err_t gnss_manager_start(void);

// Thread-safe snapshot for other firmware modules
esp_err_t gnss_manager_get_snapshot(
    gnss_snapshot_t *out
);