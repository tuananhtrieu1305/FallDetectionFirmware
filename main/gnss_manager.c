#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include <limits.h>
#include <inttypes.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "freertos/queue.h"

#include "driver/uart.h"
#include "soc/uart_reg.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "gnss_manager.h"

/*
 * PHASE 6.3 - 6.5
 * NEO-M8N NMEA Parser + Last Known Location
 *
 * GNSS TXD -> ESP32 GPIO15
 * GNSS GND -> ESP32 GND
 *
 * UART1 / 9600 baud / 8N1
 *
 * Real GNSS data and simulated test data
 * are completely separated.
 */

#define GNSS_UART                  UART_NUM_1
#define GNSS_RX_GPIO               15
#define GNSS_BAUD_RATE             9600

#define GNSS_RX_BUFFER_SIZE        2048
#define GNSS_CHUNK_SIZE            128
#define GNSS_LINE_SIZE             256

#define GNSS_TASK_STACK            4096
#define GNSS_TASK_PRIORITY         3

#define GNSS_READ_TIMEOUT_MS       100
#define GNSS_STATUS_PERIOD_MS      5000

// No fresh RMC fix for 3 seconds -> LAST_KNOWN
#define GNSS_FIX_STALE_US          3000000LL

// Temporary live-UART diagnostic; set to 0 and rebuild to disable.
#define GNSS_RAW_DIAGNOSTIC        1
#define GNSS_RAW_SAMPLE_SIZE       128
#define GNSS_RAW_LOG_ROW_SIZE      32
#define GNSS_UART_EVENT_QUEUE_SIZE 32

static const char *TAG = "GNSS";

/* =========================================================
 * GNSS internal state
 * ========================================================= */

typedef struct {
    bool fix_reported;
    bool has_current;
    bool has_last_known;

    uint8_t satellites_used;
    uint32_t rmc_time_of_day_ms;

    gnss_location_t current;
    gnss_location_t last_known;
} gnss_state_t;

static gnss_state_t s_state;

static SemaphoreHandle_t s_state_mutex = NULL;

static bool s_started = false;
static QueueHandle_t s_uart_events = NULL;

/* =========================================================
 * Numeric helpers
 * ========================================================= */

static bool two_digits(const char *p, int *out)
{
    if (p[0] < '0' || p[0] > '9' ||
        p[1] < '0' || p[1] > '9') {
        return false;
    }

    *out = (p[0] - '0') * 10 + (p[1] - '0');

    return true;
}

/* =========================================================
 * Parse UTC time: hhmmss.sss
 * ========================================================= */

static bool parse_utc_time(
    const char *text,
    uint32_t *ms_of_day)
{
    if (!text || strlen(text) < 6) {
        return false;
    }

    int hour;
    int minute;
    int second;

    if (!two_digits(text, &hour) ||
        !two_digits(text + 2, &minute) ||
        !two_digits(text + 4, &second)) {
        return false;
    }

    if (hour > 23 || minute > 59 || second > 59) {
        return false;
    }

    unsigned int milliseconds = 0;
    const char *p = text + 6;

    if (*p == '.') {
        ++p;

        if (*p < '0' || *p > '9') {
            return false;
        }

        unsigned int multiplier = 100;

        while (*p >= '0' && *p <= '9') {
            if (multiplier) {
                milliseconds +=
                    (unsigned int)(*p - '0') * multiplier;

                multiplier /= 10;
            }

            ++p;
        }
    }

    if (*p != '\0') {
        return false;
    }

    *ms_of_day =
        (uint32_t)((hour * 3600 +
                    minute * 60 +
                    second) * 1000) +
        milliseconds;

    return true;
}

/* =========================================================
 * UTC date conversion
 * ========================================================= */

static bool leap_year(int year)
{
    return year % 4 == 0 &&
           (year % 100 != 0 || year % 400 == 0);
}

static bool parse_utc_date(
    const char *text,
    int64_t *days_since_epoch)
{
    if (!text || strlen(text) != 6) {
        return false;
    }

    int day;
    int month;
    int yy;

    if (!two_digits(text, &day) ||
        !two_digits(text + 2, &month) ||
        !two_digits(text + 4, &yy)) {
        return false;
    }

    int year = yy >= 80 ? 1900 + yy : 2000 + yy;

    const int days_in_month[12] = {
        31, 28, 31, 30, 31, 30,
        31, 31, 30, 31, 30, 31
    };

    if (month < 1 || month > 12 || day < 1) {
        return false;
    }

    int max_day = days_in_month[month - 1];

    if (month == 2 && leap_year(year)) {
        max_day = 29;
    }

    if (day > max_day) {
        return false;
    }

    /*
     * Convert Gregorian civil date to days
     * since Unix epoch 1970-01-01.
     */

    int y = year - (month <= 2);

    int era = (y >= 0 ? y : y - 399) / 400;

    unsigned int yoe =
        (unsigned int)(y - era * 400);

    int adjusted_month =
        month + (month > 2 ? -3 : 9);

    unsigned int doy =
        (153U * (unsigned int)adjusted_month + 2U) / 5U
        + (unsigned int)day - 1U;

    unsigned int doe =
        yoe * 365U +
        yoe / 4U -
        yoe / 100U +
        doy;

    *days_since_epoch =
        (int64_t)era * 146097LL +
        (int64_t)doe -
        719468LL;

    return true;
}

/* =========================================================
 * Convert NMEA coordinates to decimal degrees
 *
 * Latitude:  ddmm.mmmm
 * Longitude: dddmm.mmmm
 * ========================================================= */

static bool parse_coordinate(
    const char *text,
    char hemisphere,
    bool latitude,
    double *degrees_out)
{
    const size_t deg_digits =
        latitude ? 2U : 3U;

    if (!text ||
        strlen(text) < deg_digits + 2U) {
        return false;
    }

    if (latitude
            ? (hemisphere != 'N' && hemisphere != 'S')
            : (hemisphere != 'E' && hemisphere != 'W')) {
        return false;
    }

    int degrees = 0;

    for (size_t i = 0; i < deg_digits; ++i) {
        if (text[i] < '0' || text[i] > '9') {
            return false;
        }

        degrees = degrees * 10 + text[i] - '0';
    }

    const char *p = text + deg_digits;

    if (p[0] < '0' || p[0] > '9' ||
        p[1] < '0' || p[1] > '9') {
        return false;
    }

    const char *fraction = p + 2;

    if (*fraction == '.') {
        ++fraction;

        if (*fraction < '0' || *fraction > '9') {
            return false;
        }

        while (*fraction >= '0' &&
               *fraction <= '9') {
            ++fraction;
        }
    }

    if (*fraction != '\0') {
        return false;
    }

    char *end;

    double minutes = strtod(p, &end);

    if (*end != '\0' ||
        !isfinite(minutes) ||
        minutes < 0.0 ||
        minutes >= 60.0) {
        return false;
    }

    double value = degrees + minutes / 60.0;

    if (value > (latitude ? 90.0 : 180.0)) {
        return false;
    }

    if (hemisphere == 'S' || hemisphere == 'W') {
        value = -value;
    }

    *degrees_out = value;

    return true;
}

/* =========================================================
 * NMEA checksum verification
 * ========================================================= */

static int hex_nibble(char c)
{
    if (c >= '0' && c <= '9') {
        return c - '0';
    }

    if (c >= 'A' && c <= 'F') {
        return c - 'A' + 10;
    }

    if (c >= 'a' && c <= 'f') {
        return c - 'a' + 10;
    }

    return -1;
}

static bool verified_payload(
    const char *line,
    char *out,
    size_t out_size)
{
    if (!line || line[0] != '$') {
        return false;
    }

    const char *star = strchr(line + 1, '*');

    if (!star ||
        star[1] == '\0' ||
        star[2] == '\0' ||
        star[3] != '\0') {
        return false;
    }

    int hi = hex_nibble(star[1]);
    int lo = hex_nibble(star[2]);

    if (hi < 0 || lo < 0) {
        return false;
    }

    size_t length =
        (size_t)(star - (line + 1));

    if (length < 5 || length >= out_size) {
        return false;
    }

    unsigned char checksum = 0;

    for (const char *p = line + 1; p < star; ++p) {
        checksum ^= (unsigned char)*p;
    }

    if (checksum !=
        (unsigned char)((hi << 4) | lo)) {
        return false;
    }

    memcpy(out, line + 1, length);
    out[length] = '\0';

    return true;
}

/* =========================================================
 * Split comma-delimited NMEA fields
 * ========================================================= */

static size_t split_fields(
    char *payload,
    char **fields,
    size_t capacity)
{
    size_t count = 0;

    fields[count++] = payload;

    for (char *p = payload; *p; ++p) {
        if (*p == ',') {
            *p = '\0';

            if (count >= capacity) {
                return 0;
            }

            fields[count++] = p + 1;
        }
    }

    return count;
}

static bool parse_satellites(
    const char *text,
    uint8_t *count)
{
    if (!text || !*text) {
        return false;
    }

    unsigned int value = 0;

    for (const char *p = text; *p; ++p) {
        if (*p < '0' || *p > '9') {
            return false;
        }

        value =
            value * 10U +
            (unsigned int)(*p - '0');

        if (value > UINT8_MAX) {
            return false;
        }
    }

    *count = (uint8_t)value;

    return true;
}

/* =========================================================
 * Apply one valid NMEA sentence to a state
 *
 * This is shared between:
 * - real UART processing
 * - offline self-tests
 * ========================================================= */

static bool apply_nmea(
    gnss_state_t *state,
    const char *line,
    int64_t now_us)
{
    char payload[GNSS_LINE_SIZE];
    char *fields[24];

    if (!verified_payload(
            line,
            payload,
            sizeof(payload))) {
        return false;
    }

    size_t count =
        split_fields(payload, fields, 24);

    if (count == 0 ||
        strlen(fields[0]) != 5) {
        return false;
    }

    // Accept GP, GN, GL and other talkers.
    const char *message = fields[0] + 2;

    /* -----------------------------------------------------
     * RMC: time, status, coordinates, date
     * ----------------------------------------------------- */

    if (strcmp(message, "RMC") == 0) {
        if (count < 10) {
            return false;
        }

        if (strcmp(fields[2], "A") != 0 ||
            (count > 12 &&
             strcmp(fields[12], "N") == 0)) {
            state->fix_reported = false;
            return true;
        }

        uint32_t ms_of_day;
        int64_t days;

        double lat;
        double lon;

        if (!parse_utc_time(
                fields[1],
                &ms_of_day) ||
            !parse_utc_date(
                fields[9],
                &days) ||
            !parse_coordinate(
                fields[3],
                fields[4][0],
                true,
                &lat) ||
            !parse_coordinate(
                fields[5],
                fields[6][0],
                false,
                &lon)) {

            state->fix_reported = false;
            return true;
        }

        gnss_location_t location = {
            .latitude_deg = lat,
            .longitude_deg = lon,

            .satellites_used =
                state->satellites_used,

            .observed_at_utc_ms =
                days * 86400000LL + ms_of_day,

            .received_at_monotonic_us = now_us
        };

        state->current = location;
        state->last_known = location;

        state->has_current = true;
        state->has_last_known = true;

        state->fix_reported = true;
        state->rmc_time_of_day_ms = ms_of_day;

        return true;
    }

    /* -----------------------------------------------------
     * GGA: fix quality and satellites used
     * ----------------------------------------------------- */

    if (strcmp(message, "GGA") == 0) {
        if (count < 8) {
            return false;
        }

        char *end;

        long quality =
            strtol(fields[6], &end, 10);

        if (fields[6][0] == '\0' ||
            *end != '\0' ||
            quality < 0 ||
            quality > 8) {
            return false;
        }

        uint8_t satellites = 0;

        if (!parse_satellites(
                fields[7],
                &satellites)) {
            return false;
        }

        if (quality == 0) {
            state->fix_reported = false;
            state->satellites_used = 0;
        } else {
            state->satellites_used = satellites;

            uint32_t time_of_day;

            if (state->fix_reported &&
                state->has_current &&
                parse_utc_time(
                    fields[1],
                    &time_of_day) &&
                time_of_day / 1000U ==
                state->rmc_time_of_day_ms / 1000U) {

                state->current.satellites_used =
                    satellites;

                state->last_known.satellites_used =
                    satellites;
            }
        }

        return true;
    }

    // Other NMEA messages are ignored in this phase.
    return false;
}

/* =========================================================
 * Produce Current / Last Known / Unavailable snapshot
 * ========================================================= */

static void make_snapshot(
    const gnss_state_t *state,
    int64_t now_us,
    gnss_snapshot_t *out)
{
    memset(out, 0, sizeof(*out));

    out->source = GNSS_LOCATION_UNAVAILABLE;
    out->location_age_ms = UINT32_MAX;

    out->has_last_known = state->has_last_known;

    if (state->has_last_known) {
        out->last_known_location =
            state->last_known;
    }

    int64_t age_us =
        now_us -
        state->current.received_at_monotonic_us;

    if (state->fix_reported &&
        state->has_current &&
        age_us >= 0 &&
        age_us <= GNSS_FIX_STALE_US) {

        out->source = GNSS_LOCATION_CURRENT;
        out->fix_valid = true;
        out->has_current = true;

        out->current_location =
            state->current;

        out->effective_location =
            state->current;

    } else if (state->has_last_known) {

        out->source = GNSS_LOCATION_LAST_KNOWN;

        out->effective_location =
            state->last_known;
    }

    if (out->source != GNSS_LOCATION_UNAVAILABLE) {
        age_us =
            now_us -
            out->effective_location
                .received_at_monotonic_us;

        if (age_us < 0) {
            age_us = 0;
        }

        out->location_age_ms =
            age_us / 1000 > UINT32_MAX
                ? UINT32_MAX
                : (uint32_t)(age_us / 1000);
    }
}

/* =========================================================
 * Offline NMEA self-tests
 *
 * Synthetic data stays in local test state.
 * No simulated location reaches s_state.
 * ========================================================= */

static bool run_selftests(void)
{
    const int64_t t0 = 10000000LL;

    gnss_state_t test = {0};
    gnss_snapshot_t shot;

    // TEST 1: No previous fix -> unavailable
    make_snapshot(&test, t0, &shot);

    if (shot.source != GNSS_LOCATION_UNAVAILABLE) {
        return false;
    }

    // TEST 2: Standard valid RMC + GGA
    if (!apply_nmea(
        &test,
        "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A",
        t0)) {
        return false;
    }

    if (!apply_nmea(
        &test,
        "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47",
        t0 + 100000)) {
        return false;
    }

    make_snapshot(&test, t0 + 100000, &shot);

    if (shot.source != GNSS_LOCATION_CURRENT ||
        !shot.fix_valid ||
        shot.effective_location.satellites_used != 8 ||
        fabs(
            shot.effective_location.latitude_deg -
            48.1173
        ) > 0.000001 ||
        fabs(
            shot.effective_location.longitude_deg -
            11.5166666667
        ) > 0.000001 ||
        shot.effective_location.observed_at_utc_ms !=
            764426119000LL) {
        return false;
    }

    // TEST 3: Reject bad checksum
    if (apply_nmea(
        &test,
        "$GNRMC,,V,,,,,,,,,,N,V*00",
        t0 + 200000)) {
        return false;
    }

    make_snapshot(&test, t0 + 200000, &shot);

    if (shot.source != GNSS_LOCATION_CURRENT) {
        return false;
    }

    // TEST 4: Stale after 3 seconds
    make_snapshot(&test, t0 + 4000000, &shot);

    if (shot.source != GNSS_LOCATION_LAST_KNOWN ||
        shot.fix_valid ||
        shot.effective_location.observed_at_utc_ms !=
            764426119000LL) {
        return false;
    }

    // TEST 5: Real no-fix RMC from NEO-M8N
    if (!apply_nmea(
        &test,
        "$GNRMC,,V,,,,,,,,,,N,V*37",
        t0 + 4100000)) {
        return false;
    }

    make_snapshot(&test, t0 + 4100000, &shot);

    if (shot.source != GNSS_LOCATION_LAST_KNOWN ||
        shot.fix_valid) {
        return false;
    }

    // TEST 6: Simulated reacquisition
    if (!apply_nmea(
        &test,
        "$GNRMC,061000.00,A,2101.8000,N,10551.0000,E,0.0,0.0,261026,,,A,A*21",
        t0 + 5000000)) {
        return false;
    }

    if (!apply_nmea(
        &test,
        "$GNGGA,061000.00,2101.8000,N,10551.0000,E,1,08,1.0,10.0,M,0.0,M,,*77",
        t0 + 5100000)) {
        return false;
    }

    make_snapshot(&test, t0 + 5200000, &shot);

    if (shot.source != GNSS_LOCATION_CURRENT ||
        fabs(
            shot.effective_location.latitude_deg -
            21.03
        ) > 0.000001 ||
        fabs(
            shot.effective_location.longitude_deg -
            105.85
        ) > 0.000001 ||
        shot.effective_location.observed_at_utc_ms !=
            1792995000000LL ||
        shot.effective_location.satellites_used != 8) {
        return false;
    }

    // TEST 7: GGA no-fix -> preserve Last Known
    if (!apply_nmea(
        &test,
        "$GNGGA,,,,,,0,00,99.99,,,,,,*56",
        t0 + 5300000)) {
        return false;
    }

    make_snapshot(&test, t0 + 5400000, &shot);

    if (shot.source != GNSS_LOCATION_LAST_KNOWN ||
        shot.fix_valid ||
        shot.effective_location.observed_at_utc_ms !=
            1792995000000LL) {
        return false;
    }

    return true;
}

/* =========================================================
 * Thread-safe snapshot API
 * ========================================================= */

esp_err_t gnss_manager_get_snapshot(
    gnss_snapshot_t *out)
{
    if (!out) {
        return ESP_ERR_INVALID_ARG;
    }

    if (!s_state_mutex) {
        return ESP_ERR_INVALID_STATE;
    }

    if (xSemaphoreTake(
            s_state_mutex,
            pdMS_TO_TICKS(20)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    make_snapshot(
        &s_state,
        esp_timer_get_time(),
        out
    );

    xSemaphoreGive(s_state_mutex);

    return ESP_OK;
}

/* =========================================================
 * Bounded diagnostics, owned exclusively by the GNSS task.
 * Sample bytes before any NMEA filtering; never read UART here.
 * All counters below cover one status interval, not lifetime totals.
 * ========================================================= */

typedef struct {
    uint8_t raw[GNSS_RAW_SAMPLE_SIZE];
    size_t raw_used;
    uint32_t rx_bytes;
    uint32_t read_errors;
    uint32_t frame_errors;
    uint32_t fifo_overflows;
    uint32_t buffer_full;
    uint32_t parity_errors;
    uint32_t breaks;
    uint32_t queue_at_capacity;
    uint32_t lines;
    uint32_t invalid_nmea;
    uint32_t invalid_fields;
    uint32_t ignored_messages;
    uint32_t mutex_skips;
    uint32_t resyncs;
    uint32_t nonprint_aborts;
    uint32_t overlong_aborts;
    uint32_t outside_sentence;
} gnss_rx_diag_t;

static void collect_uart_events(gnss_rx_diag_t *diag)
{
    // Observe metadata only. Do not flush RX or reset the parser on errors.
    UBaseType_t pending = uxQueueMessagesWaiting(s_uart_events);
    if (pending == GNSS_UART_EVENT_QUEUE_SIZE) {
        ++diag->queue_at_capacity;
    }

    uart_event_t event;
    for (UBaseType_t i = 0; i < pending; ++i) {
        if (xQueueReceive(s_uart_events, &event, 0) != pdTRUE) {
            break;
        }
        switch (event.type) {
        case UART_FRAME_ERR:   ++diag->frame_errors; break;
        case UART_FIFO_OVF:    ++diag->fifo_overflows; break;
        case UART_BUFFER_FULL: ++diag->buffer_full; break;
        case UART_PARITY_ERR:  ++diag->parity_errors; break;
        case UART_BREAK:       ++diag->breaks; break;
        default: break; // UART_DATA is already consumed by uart_read_bytes().
        }
    }
}

static void diagnose_rejected_nmea(
    const char *sentence,
    gnss_rx_diag_t *diag)
{
    // Reuse validation only for diagnostics after apply_nmea returned false.
    // Neither the parser nor the location state is modified here.
    char payload[GNSS_LINE_SIZE];
    char *fields[24];
    if (!verified_payload(sentence, payload, sizeof(payload))) {
        ++diag->invalid_nmea;
        return;
    }
    size_t count = split_fields(payload, fields, 24);
    if (count == 0 || strlen(fields[0]) != 5 ||
        strcmp(fields[0] + 2, "RMC") == 0 ||
        strcmp(fields[0] + 2, "GGA") == 0) {
        ++diag->invalid_fields;
    } else {
        ++diag->ignored_messages;
    }
}

static void report_rx_diagnostics(const gnss_rx_diag_t *diag)
{
    static const char hex_digits[] = "0123456789ABCDEF";

    ESP_LOGI(TAG, "RAW_RX window: rx=%" PRIu32 " sampled=%u suppressed=%" PRIu32
             " (first <=128 UART bytes / >=5s)",
             diag->rx_bytes, (unsigned int)diag->raw_used,
             diag->rx_bytes - (uint32_t)diag->raw_used);

    // Small fixed buffers keep the existing 4096-byte task stack bounded.
    for (size_t offset = 0; offset < diag->raw_used;
         offset += GNSS_RAW_LOG_ROW_SIZE) {
        char ascii[GNSS_RAW_LOG_ROW_SIZE * 4 + 1];
        char hex[GNSS_RAW_LOG_ROW_SIZE * 3 + 1];
        size_t ascii_used = 0;
        size_t hex_used = 0;
        size_t length = diag->raw_used - offset;
        if (length > GNSS_RAW_LOG_ROW_SIZE) {
            length = GNSS_RAW_LOG_ROW_SIZE;
        }
        bool nonprint = false;
        for (size_t i = 0; i < length; ++i) {
            uint8_t byte = diag->raw[offset + i];
            hex[hex_used++] = hex_digits[byte >> 4];
            hex[hex_used++] = hex_digits[byte & 0x0f];
            hex[hex_used++] = ' ';
            if (byte >= 32 && byte <= 126) {
                // Escape backslash so literal text cannot mimic an escaped byte.
                if (byte == '\\') {
                    ascii[ascii_used++] = '\\';
                }
                ascii[ascii_used++] = (char)byte;
            } else {
                nonprint = true;
                ascii[ascii_used++] = '\\';
                if (byte == '\r' || byte == '\n' || byte == '\t') {
                    ascii[ascii_used++] = byte == '\r' ? 'r' :
                                          byte == '\n' ? 'n' : 't';
                } else {
                    ascii[ascii_used++] = 'x';
                    ascii[ascii_used++] = hex_digits[byte >> 4];
                    ascii[ascii_used++] = hex_digits[byte & 0x0f];
                }
            }
        }
        ascii[ascii_used] = '\0';
        hex[hex_used] = '\0';
        ESP_LOGI(TAG, "RAW_RX ASCII +%03u len=%u: %s",
                 (unsigned int)offset, (unsigned int)length, ascii);
        if (nonprint) {
            ESP_LOGI(TAG, "RAW_RX HEX   +%03u len=%u: %s",
                     (unsigned int)offset, (unsigned int)length, hex);
        }
    }

    esp_log_level_t level =
        (diag->frame_errors || diag->fifo_overflows || diag->buffer_full ||
         diag->parity_errors || diag->breaks || diag->read_errors ||
         diag->queue_at_capacity) ? ESP_LOG_WARN : ESP_LOG_INFO;
    ESP_LOG_LEVEL(level, TAG,
        "UART_RX_DIAG: frame=%" PRIu32 " fifo_ovf=%" PRIu32
        " buffer_full=%" PRIu32 " parity=%" PRIu32 " break=%" PRIu32
        " read_err=%" PRIu32 " queue_at_capacity=%" PRIu32
        " (observed events; queue saturation may lose events)",
        diag->frame_errors, diag->fifo_overflows, diag->buffer_full,
        diag->parity_errors, diag->breaks, diag->read_errors,
        diag->queue_at_capacity);
    ESP_LOGI(TAG,
        "NMEA_RX_DIAG: lines=%" PRIu32 " checksum_or_syntax=%" PRIu32
        " fields_or_header=%" PRIu32 " ignored_other=%" PRIu32
        " mutex_skip=%" PRIu32 " resync=%" PRIu32
        " nonprint_abort=%" PRIu32 " overlong_abort=%" PRIu32
        " outside_sentence_bytes=%" PRIu32,
        diag->lines, diag->invalid_nmea, diag->invalid_fields,
        diag->ignored_messages, diag->mutex_skips, diag->resyncs,
        diag->nonprint_aborts, diag->overlong_aborts, diag->outside_sentence);
}

/* =========================================================
 * Real GNSS UART task
 * ========================================================= */

static void gnss_task(void *arg)
{
    (void)arg;

    uint8_t chunk[GNSS_CHUNK_SIZE];
    char sentence[GNSS_LINE_SIZE];

    size_t used = 0;
    bool collecting = false;

    uint32_t total_bytes = 0;
    uint32_t parsed = 0;
    gnss_rx_diag_t diag = {0};

    TickType_t last_report =
        xTaskGetTickCount();

    ESP_LOGI(
        TAG,
        "UART1 RX GPIO15 / 9600; listening for live NMEA"
    );
    if (GNSS_RAW_DIAGNOSTIC) {
        ESP_LOGI(TAG, "GNSS RAW RX DIAGNOSTIC ON: <=128 real UART bytes / 5s; "
                 "ASCII escaped, HEX for rows containing nonprintable bytes");
    }

    while (true) {
        int received = uart_read_bytes(
            GNSS_UART,
            chunk,
            sizeof(chunk),
            pdMS_TO_TICKS(GNSS_READ_TIMEOUT_MS)
        );

        if (GNSS_RAW_DIAGNOSTIC) {
            collect_uart_events(&diag);
            if (received < 0) {
                ++diag.read_errors;
            }
        }

        if (received > 0) {
            total_bytes += (uint32_t)received;
            if (GNSS_RAW_DIAGNOSTIC) {
                diag.rx_bytes += (uint32_t)received;
                size_t sample_length = sizeof(diag.raw) - diag.raw_used;
                if (sample_length > (size_t)received) {
                    sample_length = (size_t)received;
                }
                memcpy(diag.raw + diag.raw_used, chunk, sample_length);
                diag.raw_used += sample_length;
            }

            for (int i = 0; i < received; ++i) {
                char c = (char)chunk[i];

                if (c == '$') {
                    if (GNSS_RAW_DIAGNOSTIC && collecting) {
                        ++diag.resyncs;
                    }
                    collecting = true;
                    used = 0;
                    sentence[used++] = c;

                } else if (collecting && c == '\r') {
                    continue;

                } else if (collecting && c == '\n') {
                    sentence[used] = '\0';
                    if (GNSS_RAW_DIAGNOSTIC) {
                        ++diag.lines;
                    }

                    bool applied = false;

                    if (xSemaphoreTake(
                            s_state_mutex,
                            pdMS_TO_TICKS(20)) == pdTRUE) {

                        applied = apply_nmea(
                            &s_state,
                            sentence,
                            esp_timer_get_time()
                        );

                        xSemaphoreGive(s_state_mutex);
                        if (GNSS_RAW_DIAGNOSTIC && !applied) {
                            diagnose_rejected_nmea(sentence, &diag);
                        }
                    } else if (GNSS_RAW_DIAGNOSTIC) {
                        ++diag.mutex_skips;
                    }

                    if (applied) {
                        ++parsed;
                    }

                    collecting = false;
                    used = 0;

                } else if (collecting &&
                           c >= 32 &&
                           c <= 126 &&
                           used < sizeof(sentence) - 1) {

                    sentence[used++] = c;

                } else {
                    if (GNSS_RAW_DIAGNOSTIC) {
                        if (!collecting) {
                            ++diag.outside_sentence;
                        } else if (c >= 32 && c <= 126) {
                            ++diag.overlong_aborts;
                        } else {
                            ++diag.nonprint_aborts;
                        }
                    }
                    collecting = false;
                    used = 0;
                }
            }
        }

        TickType_t now = xTaskGetTickCount();

        if ((now - last_report) >=
            pdMS_TO_TICKS(GNSS_STATUS_PERIOD_MS)) {

            gnss_snapshot_t snapshot;

            if (gnss_manager_get_snapshot(
                    &snapshot) == ESP_OK) {

                if (snapshot.source ==
                    GNSS_LOCATION_UNAVAILABLE) {

                    ESP_LOGW(
                        TAG,
                        "LOCATION UNAVAILABLE | no valid fix yet"
                    );

                } else {
                    ESP_LOGI(
                        TAG,
                        "LOCATION %s | lat=%.6f lon=%.6f | sat=%u | "
                        "fixValid=%d | observedAtUTCms=%" PRId64
                        " | age=%" PRIu32 "ms",

                        snapshot.source ==
                            GNSS_LOCATION_CURRENT
                            ? "CURRENT"
                            : "LAST_KNOWN",

                        snapshot.effective_location.latitude_deg,
                        snapshot.effective_location.longitude_deg,

                        (unsigned int)
                            snapshot.effective_location.satellites_used,

                        (int)snapshot.fix_valid,

                        snapshot.effective_location.observed_at_utc_ms,

                        snapshot.location_age_ms
                    );
                }
            }

            ESP_LOGI(
                TAG,
                "RX total=%" PRIu32
                " bytes | parsed RMC/GGA=%" PRIu32,
                total_bytes,
                parsed
            );

            if (GNSS_RAW_DIAGNOSTIC) {
                report_rx_diagnostics(&diag);
                memset(&diag, 0, sizeof(diag));
            }
            // Space diagnostic bursts >=5 seconds apart, including log time.
            last_report = GNSS_RAW_DIAGNOSTIC ? xTaskGetTickCount() : now;
        }
    }
}

/* =========================================================
 * GNSS Manager initialization
 * ========================================================= */

esp_err_t gnss_manager_start(void)
{
    if (s_started) {
        return ESP_ERR_INVALID_STATE;
    }

    ESP_LOGI(
        TAG,
        "PHASE 6.3-6.5: checking NMEA parser with simulated FIX/LOST/FIX"
    );

    if (!run_selftests()) {
        ESP_LOGE(
            TAG,
            "GNSS SELFTEST FAIL; real GNSS receiver not started"
        );

        return ESP_FAIL;
    }

    ESP_LOGI(
        TAG,
        "GNSS SELFTEST PASS: UTC, checksum, fix, stale, lastKnown, reacquire"
    );

    s_state_mutex = xSemaphoreCreateMutex();

    if (!s_state_mutex) {
        return ESP_ERR_NO_MEM;
    }

    memset(&s_state, 0, sizeof(s_state));

    uart_config_t config = {
        .baud_rate = GNSS_BAUD_RATE,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    esp_err_t err =
        uart_param_config(GNSS_UART, &config);

    if (err == ESP_OK) {
        err = uart_driver_install(
            GNSS_UART,
            GNSS_RX_BUFFER_SIZE,
            0,
            GNSS_RAW_DIAGNOSTIC ? GNSS_UART_EVENT_QUEUE_SIZE : 0,
            GNSS_RAW_DIAGNOSTIC ? &s_uart_events : NULL,
            0
        );
    }

    if (err != ESP_OK) {
        ESP_LOGE(
            TAG,
            "UART init failed: %s",
            esp_err_to_name(err)
        );

        vSemaphoreDelete(s_state_mutex);
        s_state_mutex = NULL;

        return err;
    }

    err = uart_set_pin(
        GNSS_UART,
        UART_PIN_NO_CHANGE,
        GNSS_RX_GPIO,
        UART_PIN_NO_CHANGE,
        UART_PIN_NO_CHANGE
    );

    if (err == ESP_OK && GNSS_RAW_DIAGNOSTIC) {
        // IDF v5.5.5 defaults enable overflow/parity/break, but not framing.
        // Add only the framing interrupt; keep RX thresholds/config unchanged.
        err = uart_enable_intr_mask(GNSS_UART, UART_FRM_ERR_INT_ENA_M);
    }

    if (err != ESP_OK) {
        uart_driver_delete(GNSS_UART);

        vSemaphoreDelete(s_state_mutex);
        s_state_mutex = NULL;

        return err;
    }

    if (xTaskCreate(
            gnss_task,
            "gnss_task",
            GNSS_TASK_STACK,
            NULL,
            GNSS_TASK_PRIORITY,
            NULL) != pdPASS) {

        uart_driver_delete(GNSS_UART);

        vSemaphoreDelete(s_state_mutex);
        s_state_mutex = NULL;

        return ESP_ERR_NO_MEM;
    }

    s_started = true;

    ESP_LOGI(
        TAG,
        "GNSS manager started; real NMEA separate from selftest data"
    );

    return ESP_OK;
}
