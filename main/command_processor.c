#include "command_processor.h"
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "cJSON.h"
#include "esp_log.h"
#include "alert_manager.h"

#define CACHE_SIZE 16U
typedef struct {
    char command_id[65], event_id[37], command[33], issued_at[21];
    int64_t issued_ms, processed_ms;
    const char *result, *reason;
} command_record_t;
static command_record_t s_cache[CACHE_SIZE], s_ack;
static unsigned s_count, s_next;
static bool s_enabled, s_pending;
static char s_active_event[37];
static int64_t s_stop_deadline;
static const char *TAG = "COMMAND_PROCESSOR";

static bool identifier(const char *s, size_t max)
{
    size_t n = s ? strnlen(s, max + 1) : 0;
    if (n == 0 || n > max) return false;
    for (size_t i = 0; i < n; ++i)
        if (!((s[i] >= 'a' && s[i] <= 'z') || (s[i] >= 'A' && s[i] <= 'Z') ||
              (s[i] >= '0' && s[i] <= '9') || s[i] == '-' || s[i] == '_')) return false;
    return true;
}

static bool event_id_valid(const char *s)
{
    if (s == NULL || strlen(s) != 36) return false;
    for (unsigned i = 0; i < 36; ++i) {
        if (i == 8 || i == 13 || i == 18 || i == 23) { if (s[i] != '-') return false; }
        else if (!((s[i] >= '0' && s[i] <= '9') || (s[i] >= 'a' && s[i] <= 'f'))) return false;
    }
    return true;
}

/* UTC only; no local timezone/mktime normalization of invalid calendar dates. */
static int64_t parse_utc(const char *s)
{
    if (s == NULL || strlen(s) != 20) return -1;
    const char *shape = "0000-00-00T00:00:00Z";
    for (unsigned i = 0; i < 20; ++i)
        if (shape[i] == '0' ? (s[i] < '0' || s[i] > '9') : s[i] != shape[i]) return -1;
    int y, m, d, h, min, sec;
    if (sscanf(s, "%4d-%2d-%2dT%2d:%2d:%2dZ", &y, &m, &d, &h, &min, &sec) != 6 ||
        y < 2020 || y > 2099 || m < 1 || m > 12 || h > 23 || min > 59 || sec > 59) return -1;
    const int months[] = {31,28,31,30,31,30,31,31,30,31,30,31};
    bool leap = y % 4 == 0; /* 2020..2099 includes no non-leap century. */
    if (d < 1 || d > months[m - 1] + (m == 2 && leap)) return -1;
    int days = 0;
    for (int year = 2020; year < y; ++year) days += 365 + (year % 4 == 0);
    for (int month = 1; month < m; ++month) days += months[month - 1] + (month == 2 && leap);
    days += d - 1;
    return 1577836800000LL + ((int64_t)days * 86400 + h * 3600 + min * 60 + sec) * 1000;
}

static bool parse(const mqtt_manager_command_t *f, command_record_t *out)
{
    if (f == NULL || f->length == 0 || f->length > 512 ||
        f->payload[f->length] != '\0' || memchr(f->payload, 0, f->length) != NULL) return false;
    /* Flat four-string demo schema. No escaped identifiers or nested values:
     * this also bounds cJSON allocations and rejects embedded Unicode NULs.
     */
    bool quoted = false;
    unsigned depth = 0;
    for (size_t i = 0; i < f->length; ++i) {
        char c = f->payload[i];
        if (c == '\\') return false;
        if (c == '"') quoted = !quoted;
        if (!quoted) {
            if (c == '{' && ++depth > 1) return false;
            if (c == '}' && (depth == 0 || --depth != 0)) return false;
            if (c == '[' || c == ']') return false;
        }
    }
    if (quoted || depth) return false;
    cJSON *root = cJSON_ParseWithLengthOpts(f->payload, f->length + 1, NULL, true);
    if (root == NULL) return false;
    bool valid = cJSON_IsObject(root);
    unsigned mask = 0;
    cJSON *field;
    cJSON_ArrayForEach(field, root) {
        unsigned bit = 0;
        if (!cJSON_IsString(field) || field->string == NULL) { valid = false; break; }
        const char *s = field->valuestring;
        if (!strcmp(field->string, "commandId") && identifier(s, 64)) { bit = 1; strcpy(out->command_id, s); }
        else if (!strcmp(field->string, "eventId") && event_id_valid(s)) { bit = 2; strcpy(out->event_id, s); }
        else if (!strcmp(field->string, "command") && identifier(s, 32)) { bit = 4; strcpy(out->command, s); }
        else if (!strcmp(field->string, "issuedAt") && (out->issued_ms = parse_utc(s)) >= 0) { bit = 8; strcpy(out->issued_at, s); }
        else { valid = false; break; }
        if (mask & bit) { valid = false; break; }
        mask |= bit;
    }
    cJSON_Delete(root);
    return valid && mask == 15;
}

void command_processor_init(bool enabled)
{
    s_enabled = enabled;
    s_pending = false;
    s_count = s_next = 0;
    s_stop_deadline = 0;
    s_active_event[0] = 0;
    memset(s_cache, 0, sizeof(s_cache));
    memset(&s_ack, 0, sizeof(s_ack));
}

bool command_processor_enabled(void) { return s_enabled; }
bool command_processor_ack_pending(void) { return s_pending; }
void command_processor_ack_queued(void) { s_pending = false; }

esp_err_t command_processor_arm_test(const char *event_id, int64_t now)
{
    bool on;
    if (!s_enabled || !event_id_valid(event_id) || now < 10000000LL ||
        strcmp(s_active_event, event_id) == 0) return ESP_ERR_INVALID_STATE;
    if (alert_manager_get_buzzer_state(&on) != ESP_OK || on) return ESP_ERR_INVALID_STATE;
    esp_err_t err = buzzer_start_checked();
    if (err != ESP_OK) return err;
    strcpy(s_active_event, event_id);
    s_stop_deadline = now + 30000000LL;
    ESP_LOGI(TAG, "TEST_BUZZER_ARMED eventId=%s; auto-off=30s; no rescue", s_active_event);
    return ESP_OK;
}

void command_processor_tick(int64_t now)
{
    if (s_enabled && s_stop_deadline && now >= s_stop_deadline) {
        esp_err_t err = buzzer_stop_checked();
        s_stop_deadline = err == ESP_OK ? 0 : now + 1000000LL;
        ESP_LOGW(TAG, "TEST_BUZZER_TIMEOUT off_result=%d; event retained; no command ACK", (int)err);
    }
}

void command_processor_process(const mqtt_manager_command_t *frame, uint32_t epoch, int64_t utc_ms)
{
    command_record_t r = {0};
    if (!s_enabled || !parse(frame, &r)) {
        ESP_LOGW(TAG, "command ignored: profile disabled or invalid flat JSON/schema/length");
        return;
    }
    for (unsigned i = 0; i < s_count; ++i) {
        const command_record_t *old = &s_cache[i];
        if (strcmp(old->command_id, r.command_id)) continue;
        if (!strcmp(old->event_id, r.event_id) && !strcmp(old->command, r.command) && !strcmp(old->issued_at, r.issued_at)) {
            s_ack = *old;
            s_pending = true;
            ESP_LOGI(TAG, "duplicate commandId=%s; cached result, no actuator execution", r.command_id);
            return;
        }
        r.result = "REJECTED"; r.reason = "COMMAND_ID_REUSED";
        r.processed_ms = utc_ms;
        s_ack = r; s_pending = true;
        return; /* Keep original cache entry. */
    }
    r.result = "REJECTED";
    r.processed_ms = utc_ms;
    bool on = false;
    if (frame->connection_epoch != epoch) r.reason = "STALE_CONNECTION";
    else if (strcmp(r.command, "STOP_BUZZER")) r.reason = "UNSUPPORTED_COMMAND";
    else if (utc_ms < 0) r.reason = "CLOCK_UNAVAILABLE";
    else if (utc_ms - r.issued_ms > 30000) r.reason = "EXPIRED";
    else if (r.issued_ms - utc_ms > 5000) r.reason = "FUTURE_ISSUED_AT";
    else if (!s_active_event[0] || strcmp(r.event_id, s_active_event)) r.reason = "EVENT_NOT_ACTIVE";
    else if (alert_manager_get_buzzer_state(&on) != ESP_OK) { r.result = "FAILED"; r.reason = "ACTUATOR_UNAVAILABLE"; }
    else if (!on) r.reason = "NOT_BUZZING";
    else if (buzzer_stop_checked() != ESP_OK) { r.result = "FAILED"; r.reason = "STOP_FAILED"; }
    else {
        /* Checked driver operation and readback have completed before success. */
        r.result = "EXECUTED"; r.reason = "STOPPED";
        s_stop_deadline = 0;
        ESP_LOGI(TAG, "STOP_BUZZER EXECUTED commandId=%s eventId=%s; output verified off; event retained",
                 r.command_id, r.event_id);
    }
    s_cache[s_next] = r;
    s_next = (s_next + 1) % CACHE_SIZE;
    if (s_count < CACHE_SIZE) ++s_count;
    s_ack = r;
    s_pending = true;
}

size_t command_processor_ack_json(char *out, size_t capacity)
{
    if (s_ack.result == NULL) return 0;
    char processed[24] = "null";
    if (s_ack.processed_ms >= 1577836800000LL && s_ack.processed_ms < 4102444800000LL) {
        time_t sec = (time_t)(s_ack.processed_ms / 1000);
        struct tm utc;
#ifdef _WIN32
        if (gmtime_s(&utc, &sec) == 0)
#else
        if (gmtime_r(&sec, &utc) != NULL)
#endif
            strftime(processed, sizeof(processed), "\"%Y-%m-%dT%H:%M:%SZ\"", &utc);
    }
    int n = snprintf(out, capacity, "{\"commandId\":\"%s\",\"eventId\":\"%s\",\"command\":\"%s\","
        "\"result\":\"%s\",\"reason\":\"%s\",\"processedAt\":%s}", s_ack.command_id,
        s_ack.event_id, s_ack.command, s_ack.result, s_ack.reason, processed);
    return n > 0 && (size_t)n < capacity ? (size_t)n : 0;
}
