
#include "sensor_manager.h"
#include "sensor_sample.h"
#include "sensor_ring.h"

#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"

/*
 * PHASE 5.6b: paced CSV over Serial.
 * Preserve 100Hz BMI270 + 25Hz BMP388, PSRAM PRE/POST snapshot,
 * sensor-v1 CSV, metadata and IEEE CRC32.
 * All UART output stays in the lower-priority logger task.
 * Logger yields after each small group of CSV rows to prevent
 * starvation of the CPU1 idle task (and the Task Watchdog).
 * This build uses one synthetic event per boot; no fall inference.
 */
#define SENSOR_TASK_STACK_BYTES   6144U
#define SENSOR_TASK_PRIORITY      12U
#define LOGGER_TASK_STACK_BYTES   4096U
#define LOGGER_TASK_PRIORITY      4U
#define DIAG_QUEUE_LENGTH         32U
#define CSV_ROWS_PER_YIELD        8U
#define CSV_YIELD_TICKS           1U
#define DIAG_WINDOW_US            5000000LL
#define PRESSURE_MAX_AGE_US       200000LL
#define GAP_LOWER_LIMIT_US        8000LL
#define GAP_UPPER_LIMIT_US        12000LL
#define ACC_LSB_TO_MPS2           ((8.0f * 9.80665f) / 32768.0f)
#define GYR_LSB_TO_RADPS          ((2000.0f * 0.01745329251994329577f) / 32768.0f)
#define CSV_HEADER "timestamp_us,ax,ay,az,gx,gy,gz,pressure_pa,seq,pressure_timestamp_us,flags\n"

_Static_assert(sizeof(sensor_sample_t) == 56U,
               "sensor_sample_t size changed; update data contract");

typedef enum {
    EVENT_IDLE = 0,
    EVENT_COLLECTING = 1,
    EVENT_READY = 2,
} event_state_t;

typedef struct {
    event_state_t state;
    sensor_ring_t *frozen_pre_ring;
    uint32_t pre_start_index;
    uint32_t trigger_seq;
    uint32_t post_count;
    uint32_t early_rejected;
    uint32_t busy_rejected;
} event_capture_t;

typedef struct {
    uint32_t seq, successful, imu_errors, skipped_ticks;
    uint32_t imu_hz_x10, bmp_hz_x10;
    int64_t gap_min_us, gap_avg_us, gap_max_us;
    uint32_t gap_count, gap_short_count, gap_long_count;
    uint32_t outliers, outlier_permille;
    uint64_t total_gap_bad, total_gap_count;
    uint32_t bmp_reads, bmp_ok, bmp_errors;
    float pressure_pa;
    int64_t pressure_age_us;
    uint32_t pressure_attached;
    int64_t bmp_max_read_us;
    uint32_t dropped_diagnostics;
    uint32_t ring_count, ring_capacity, ring_last_seq;
    uint64_t ring_total_written, ring_evicted_oldest;
    uint32_t event_state, event_trigger_seq, event_post_count;
    uint32_t event_early_rejected, event_busy_rejected;
} diag_snapshot_t;

static const char *TAG = "SENSOR_MANAGER";
static TaskHandle_t s_task = NULL;
static TaskHandle_t s_logger_task = NULL;
static esp_timer_handle_t s_timer = NULL;
static QueueHandle_t s_diag_queue = NULL;
static uint32_t s_dropped_diagnostics = 0U;
static sensor_ring_t s_ring_a, s_ring_b;
static sensor_ring_t *s_active_ring = NULL;
static sensor_sample_t *s_post_storage = NULL;
static event_capture_t s_event;
static struct bmi2_dev *s_bmi = NULL;
static struct bmp3_dev *s_bmp = NULL;

/* Called only from sensor_task. This synthetic trigger does not mean a fall. */
static void event_request(uint32_t seq)
{
    if (s_event.state != EVENT_IDLE) {
        s_event.busy_rejected++;
        return;
    }
    if (s_active_ring->count < SENSOR_PRE_SAMPLES) {
        s_event.early_rejected++;
        return;
    }
    s_event.frozen_pre_ring = s_active_ring;
    s_event.pre_start_index =
        (s_active_ring->head + s_active_ring->capacity - SENSOR_PRE_SAMPLES)
        % s_active_ring->capacity;
    s_event.trigger_seq = seq;
    s_event.post_count = 0U;
    s_event.state = EVENT_COLLECTING;
    s_active_ring = (s_active_ring == &s_ring_a) ? &s_ring_b : &s_ring_a;
}

static void event_run_synthetic_requests(uint32_t seq)
{
    if (seq == 500U || seq == 4500U || seq == 4600U || seq == 5700U) {
        event_request(seq);
    }
}

/* Runs once after a READY snapshot reaches the logger via its queue. */
static bool logger_verify_event_once(void)
{
    static bool checked = false;
    static bool passed = false;
    if (checked) {
        return passed;
    }
    if (s_event.state != EVENT_READY) {
        return false;
    }
    checked = true;

    const sensor_ring_t *pre = s_event.frozen_pre_ring;
    const uint32_t trigger = s_event.trigger_seq;
    uint32_t failures = 0U;
    uint32_t pre_first = 0U, pre_last = 0U;
    uint32_t post_first = 0U, post_last = 0U;
    int64_t previous_ts = 0;

    if (pre == NULL || pre->storage == NULL ||
        pre->count < SENSOR_PRE_SAMPLES ||
        s_post_storage == NULL || s_event.post_count != SENSOR_POST_SAMPLES) {
        failures++;
    } else {
        for (uint32_t i = 0; i < SENSOR_PRE_SAMPLES; i++) {
            uint32_t idx = (s_event.pre_start_index + i) % pre->capacity;
            const sensor_sample_t *p = &pre->storage[idx];
            if (i == 0U) pre_first = p->seq;
            if (i == SENSOR_PRE_SAMPLES - 1U) pre_last = p->seq;
            if (p->seq != trigger - SENSOR_PRE_SAMPLES + i ||
                (previous_ts > 0 && p->timestamp_us <= previous_ts)) {
                failures++;
            }
            previous_ts = p->timestamp_us;
        }
        for (uint32_t i = 0; i < SENSOR_POST_SAMPLES; i++) {
            const sensor_sample_t *p = &s_post_storage[i];
            if (i == 0U) post_first = p->seq;
            if (i == SENSOR_POST_SAMPLES - 1U) post_last = p->seq;
            if (p->seq != trigger + i ||
                (previous_ts > 0 && p->timestamp_us <= previous_ts)) {
                failures++;
            }
            if (i == 0U && !(p->flags & SENSOR_FLAG_EVENT_MARKER)) {
                failures++;
            }
            previous_ts = p->timestamp_us;
        }
    }

    passed = (failures == 0U);
    ESP_LOGI(TAG,
        "event_verify=%s fail_checks=%" PRIu32
        " pre_seq=%" PRIu32 "..%" PRIu32
        " post_seq=%" PRIu32 "..%" PRIu32
        " marker_first_post=%u pre_count=%u post_count=%" PRIu32,
        passed ? "PASS" : "FAIL", failures,
        pre_first, pre_last, post_first, post_last,
        s_event.post_count > 0U ?
            (unsigned)((s_post_storage[0].flags & SENSOR_FLAG_EVENT_MARKER) != 0U) : 0U,
        (unsigned)SENSOR_PRE_SAMPLES, s_event.post_count);
    return passed;
}

static uint32_t csv_crc32_update(uint32_t crc, const char *data, size_t length)
{
    for (size_t i = 0; i < length; ++i) {
        crc ^= (uint8_t)data[i];
        for (unsigned j = 0; j < 8U; ++j) {
            crc = (crc >> 1U) ^ (0xEDB88320U & (0U - (crc & 1U)));
        }
    }
    return crc;
}

/* CSV lines, including their final LF, are exactly the bytes CRC32 covers. */
static bool csv_emit_sample(const sensor_sample_t *s, uint32_t *crc)
{
    char line[240];
    int n;
    if (s->flags & SENSOR_FLAG_PRESSURE_VALID) {
        n = snprintf(line, sizeof(line),
            "%" PRId64 ",%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.2f,%" PRIu32
            ",%" PRId64 ",%" PRIu32 "\n",
            s->timestamp_us, (double)s->ax, (double)s->ay, (double)s->az,
            (double)s->gx, (double)s->gy, (double)s->gz,
            (double)s->pressure_pa, s->seq, s->pressure_timestamp_us, s->flags);
    } else {
        n = snprintf(line, sizeof(line),
            "%" PRId64 ",%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,,%" PRIu32
            ",,%" PRIu32 "\n",
            s->timestamp_us, (double)s->ax, (double)s->ay, (double)s->az,
            (double)s->gx, (double)s->gy, (double)s->gz, s->seq, s->flags);
    }
    if (n < 0 || (size_t)n >= sizeof(line) || fputs(line, stdout) == EOF) {
        return false;
    }
    *crc = csv_crc32_update(*crc, line, (size_t)n);
    return true;
}

/* Yields CPU1 frequently enough for the idle task / Task Watchdog.
 * Running on a lower-priority task alone was not sufficient in 5.6a.
 */
static inline void csv_pace_after_row(uint32_t written)
{
    if ((written % CSV_ROWS_PER_YIELD) == 0U) {
        vTaskDelay(CSV_YIELD_TICKS);
    }
}

static void logger_export_event_once(void)
{
    static bool exported = false;
    if (exported || s_event.state != EVENT_READY) return;
    exported = true;

    const sensor_ring_t *pre = s_event.frozen_pre_ring;
    if (pre == NULL || pre->storage == NULL ||
        s_post_storage == NULL || s_event.post_count != SENSOR_POST_SAMPLES) {
        ESP_LOGE(TAG, "CSV_EXPORT_ABORT invalid immutable snapshot");
        return;
    }

    const uint32_t expected = SENSOR_PRE_SAMPLES + SENSOR_POST_SAMPLES;
    uint32_t crc = 0xFFFFFFFFU;
    uint32_t written = 0U;

    printf("FDCSV_BEGIN,1,%" PRIu32 ",%" PRIu32 "\n",
           expected, s_event.trigger_seq);
    printf(
        "FDMETA,{"
        "\"schema_version\":\"sensor-v1\","
        "\"export_version\":\"5.6b\","
        "\"trigger_type\":\"synthetic_test\","
        "\"trigger_seq\":%" PRIu32 ","
        "\"pre_samples\":%u,\"post_samples\":%u,"
        "\"imu_hz\":100,\"pressure_hz\":25,"
        "\"mount_location\":\"abdomen_waist\","
        "\"axes\":\"sensor_frame_unmapped\","
        "\"accel_unit\":\"m/s2\",\"gyro_unit\":\"rad/s\","
        "\"pressure_unit\":\"Pa\","
        "\"accel_includes_gravity\":true,"
        "\"timestamp_kind\":\"esp_timer_us_monotonic_before_imu_host_read\","
        "\"pressure_sampling\":\"sample_and_hold\","
        "\"pressure_valid_bit\":1,\"event_marker_bit\":2,"
        "\"ground_truth_label\":\"unknown\""
        "}\n",
        s_event.trigger_seq, (unsigned)SENSOR_PRE_SAMPLES,
        (unsigned)SENSOR_POST_SAMPLES);

    if (fputs(CSV_HEADER, stdout) == EOF) goto fail;
    crc = csv_crc32_update(crc, CSV_HEADER, strlen(CSV_HEADER));

    for (uint32_t i = 0; i < SENSOR_PRE_SAMPLES; ++i) {
        uint32_t index = (s_event.pre_start_index + i) % pre->capacity;
        if (!csv_emit_sample(&pre->storage[index], &crc)) goto fail;
        csv_pace_after_row(++written);
    }
    for (uint32_t i = 0; i < SENSOR_POST_SAMPLES; ++i) {
        if (!csv_emit_sample(&s_post_storage[i], &crc)) goto fail;
        csv_pace_after_row(++written);
    }
    if (fflush(stdout) == EOF) goto fail;

    printf("FDCSV_END,%" PRIu32 ",%08" PRIX32 "\n",
           written, crc ^ 0xFFFFFFFFU);
    fflush(stdout);
    ESP_LOGI(TAG, "CSV_EXPORT_FINISHED rows=%" PRIu32
         " yield_every=%u yield_ticks=%u",
         written, (unsigned)CSV_ROWS_PER_YIELD, (unsigned)CSV_YIELD_TICKS);
    return;

fail:
    printf("FDCSV_ABORT,%" PRIu32 "\n", written);
    fflush(stdout);
    ESP_LOGE(TAG, "CSV_EXPORT_ABORT output error after rows=%" PRIu32, written);
}

static void logger_task(void *arg)
{
    (void)arg;
    ESP_LOGI(TAG, "PHASE 5.6b CSV_PACED: BMI270 100 Hz + BMP388 25 Hz; "
             "CSV Serial logger yield every 8 rows; AI NOT active");
    diag_snapshot_t d;
    for (;;) {
        if (xQueueReceive(s_diag_queue, &d, portMAX_DELAY) != pdTRUE) continue;
        ESP_LOGI(TAG,
            "diag_5s seq=%" PRIu32 " ok=%" PRIu32
            " imu_err=%" PRIu32 " missed_ticks=%" PRIu32
            " imu_hz=%" PRIu32 ".%01" PRIu32
            " bmp_hz=%" PRIu32 ".%01" PRIu32
            " gap_us[min/avg/max]=%" PRId64 "/%" PRId64 "/%" PRId64,
            d.seq, d.successful, d.imu_errors, d.skipped_ticks,
            d.imu_hz_x10 / 10U, d.imu_hz_x10 % 10U,
            d.bmp_hz_x10 / 10U, d.bmp_hz_x10 % 10U,
            d.gap_min_us, d.gap_avg_us, d.gap_max_us);
        ESP_LOGI(TAG,
            "diag_jitter gap_count=%" PRIu32
            " lt8ms=%" PRIu32 " gt12ms=%" PRIu32
            " outliers=%" PRIu32 " outlier_permille=%" PRIu32
            " cum_bad=%" PRIu64 "/%" PRIu64
            " bmp_reads=%" PRIu32 " bmp_ok=%" PRIu32
            " bmp_err=%" PRIu32 " pressure_pa=%.2f"
            " pressure_age_us=%" PRId64
            " pressure_attached=%" PRIu32
            " bmp_max_read_us=%" PRId64
            " diag_dropped=%" PRIu32,
            d.gap_count, d.gap_short_count, d.gap_long_count,
            d.outliers, d.outlier_permille,
            d.total_gap_bad, d.total_gap_count,
            d.bmp_reads, d.bmp_ok, d.bmp_errors,
            d.pressure_pa, d.pressure_age_us, d.pressure_attached,
            d.bmp_max_read_us, d.dropped_diagnostics);
        ESP_LOGI(TAG,
            "ring count=%" PRIu32 "/%" PRIu32
            " total_written=%" PRIu64 " evicted_oldest=%" PRIu64
            " last_seq=%" PRIu32,
            d.ring_count, d.ring_capacity,
            d.ring_total_written, d.ring_evicted_oldest, d.ring_last_seq);
        ESP_LOGI(TAG,
            "event state=%" PRIu32 " trigger_seq=%" PRIu32
            " post=%" PRIu32 "/%u early_rejected=%" PRIu32
            " busy_rejected=%" PRIu32,
            d.event_state, d.event_trigger_seq, d.event_post_count,
            (unsigned)SENSOR_POST_SAMPLES,
            d.event_early_rejected, d.event_busy_rejected);
        if (d.event_state == EVENT_READY && logger_verify_event_once()) {
            logger_export_event_once();
        }
    }
}

static void sensor_tick_cb(void *arg)
{
    (void)arg;
    if (s_task != NULL) xTaskNotifyGive(s_task);
}

/* Single writer to rings and POST storage. Never print from this task. */
static void sensor_task(void *arg)
{
    (void)arg;
    uint32_t seq = 0U, successful = 0U, imu_errors = 0U;
    uint32_t skipped_ticks = 0U, window_samples = 0U;
    uint32_t bmp_reads = 0U, bmp_ok = 0U, bmp_errors = 0U;
    uint32_t window_bmp_reads = 0U, pressure_attached = 0U;
    int64_t bmp_max_read_us = 0;
    float cached_pressure_pa = 0.0f;
    int64_t cached_pressure_timestamp_us = 0, last_imu_timestamp_us = 0;
    int64_t gap_min_us = INT64_MAX, gap_max_us = 0, gap_sum_us = 0;
    uint32_t gap_count = 0U, gap_short_count = 0U, gap_long_count = 0U;
    uint64_t total_gap_count = 0U, total_gap_bad = 0U;
    int64_t window_start_us = esp_timer_get_time();

    for (;;) {
        uint32_t pending = ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        if (pending == 0U) continue;
        seq += pending;
        skipped_ticks += pending - 1U;
        event_run_synthetic_requests(seq);

        sensor_sample_t sample;
        memset(&sample, 0, sizeof(sample));
        sample.seq = seq;
        sample.timestamp_us = esp_timer_get_time();
        if (s_event.state == EVENT_COLLECTING && seq == s_event.trigger_seq) {
            sample.flags |= SENSOR_FLAG_EVENT_MARKER;
        }
        if (cached_pressure_timestamp_us > 0 &&
            cached_pressure_timestamp_us <= sample.timestamp_us &&
            sample.timestamp_us - cached_pressure_timestamp_us <= PRESSURE_MAX_AGE_US) {
            sample.pressure_pa = cached_pressure_pa;
            sample.pressure_timestamp_us = cached_pressure_timestamp_us;
            sample.flags |= SENSOR_FLAG_PRESSURE_VALID;
            pressure_attached++;
        }

        struct bmi2_sens_data raw;
        memset(&raw, 0, sizeof(raw));
        int8_t bmi_rc = bmi2_get_sensor_data(&raw, s_bmi);
        if (bmi_rc == BMI2_OK) {
            sample.ax = (float)raw.acc.x * ACC_LSB_TO_MPS2;
            sample.ay = (float)raw.acc.y * ACC_LSB_TO_MPS2;
            sample.az = (float)raw.acc.z * ACC_LSB_TO_MPS2;
            sample.gx = (float)raw.gyr.x * GYR_LSB_TO_RADPS;
            sample.gy = (float)raw.gyr.y * GYR_LSB_TO_RADPS;
            sample.gz = (float)raw.gyr.z * GYR_LSB_TO_RADPS;
            successful++;
            window_samples++;
            sensor_ring_append(s_active_ring, &sample);
            if (s_event.state == EVENT_COLLECTING &&
                seq >= s_event.trigger_seq &&
                seq < s_event.trigger_seq + SENSOR_POST_SAMPLES &&
                s_event.post_count < SENSOR_POST_SAMPLES) {
                s_post_storage[s_event.post_count++] = sample;
            }
            if (last_imu_timestamp_us > 0) {
                int64_t gap = sample.timestamp_us - last_imu_timestamp_us;
                if (gap < gap_min_us) gap_min_us = gap;
                if (gap > gap_max_us) gap_max_us = gap;
                gap_sum_us += gap;
                gap_count++;
                total_gap_count++;
                if (gap < GAP_LOWER_LIMIT_US) {
                    gap_short_count++;
                    total_gap_bad++;
                } else if (gap > GAP_UPPER_LIMIT_US) {
                    gap_long_count++;
                    total_gap_bad++;
                }
            }
            last_imu_timestamp_us = sample.timestamp_us;
        } else {
            imu_errors++;
        }

        if (s_event.state == EVENT_COLLECTING &&
            seq >= s_event.trigger_seq + SENSOR_POST_SAMPLES - 1U) {
            s_event.state = EVENT_READY;
        }

        /* Read BMP388 after IMU, once per four scheduling ticks. */
        if ((seq % 4U) == 0U) {
            struct bmp3_data bmp_data;
            memset(&bmp_data, 0, sizeof(bmp_data));
            bmp_reads++;
            window_bmp_reads++;
            int64_t begin_us = esp_timer_get_time();
            int8_t bmp_rc = bmp3_get_sensor_data(BMP3_PRESS_TEMP, &bmp_data, s_bmp);
            int64_t read_ts = esp_timer_get_time();
            int64_t read_us = read_ts - begin_us;
            if (read_us > bmp_max_read_us) bmp_max_read_us = read_us;
            if (bmp_rc == BMP3_OK) {
#ifdef BMP3_FLOAT_COMPENSATION
                float pressure_pa = (float)bmp_data.pressure;
#else
                float pressure_pa = (float)bmp_data.pressure / 100.0f;
#endif
                if (pressure_pa > 30000.0f && pressure_pa < 120000.0f) {
                    cached_pressure_pa = pressure_pa;
                    cached_pressure_timestamp_us = read_ts;
                    bmp_ok++;
                } else {
                    bmp_errors++;
                }
            } else {
                bmp_errors++;
            }
        }

        int64_t now_us = esp_timer_get_time();
        if (now_us - window_start_us >= DIAG_WINDOW_US) {
            int64_t elapsed_us = now_us - window_start_us;
            uint32_t hz10 = (uint32_t)(((uint64_t)window_samples * 10000000ULL)
                                      / (uint64_t)elapsed_us);
            uint32_t bmp_hz10 = (uint32_t)(((uint64_t)window_bmp_reads * 10000000ULL)
                                          / (uint64_t)elapsed_us);
            uint32_t bad = gap_short_count + gap_long_count;
            diag_snapshot_t d = {
                .seq = seq,
                .successful = successful,
                .imu_errors = imu_errors,
                .skipped_ticks = skipped_ticks,
                .imu_hz_x10 = hz10,
                .bmp_hz_x10 = bmp_hz10,
                .gap_min_us = gap_count ? gap_min_us : 0,
                .gap_avg_us = gap_count ? gap_sum_us / (int64_t)gap_count : 0,
                .gap_max_us = gap_max_us,
                .gap_count = gap_count,
                .gap_short_count = gap_short_count,
                .gap_long_count = gap_long_count,
                .outliers = bad,
                .outlier_permille = gap_count ?
                    (uint32_t)((uint64_t)bad * 1000U / gap_count) : 0U,
                .total_gap_bad = total_gap_bad,
                .total_gap_count = total_gap_count,
                .bmp_reads = bmp_reads,
                .bmp_ok = bmp_ok,
                .bmp_errors = bmp_errors,
                .pressure_pa = cached_pressure_pa,
                .pressure_age_us = cached_pressure_timestamp_us > 0 ?
                    now_us - cached_pressure_timestamp_us : -1,
                .pressure_attached = pressure_attached,
                .bmp_max_read_us = bmp_max_read_us,
                .dropped_diagnostics = s_dropped_diagnostics,
                .ring_count = s_active_ring->count,
                .ring_capacity = s_active_ring->capacity,
                .ring_last_seq = s_active_ring->last_seq,
                .ring_total_written = s_active_ring->total_written,
                .ring_evicted_oldest = s_active_ring->evicted_oldest,
                .event_state = (uint32_t)s_event.state,
                .event_trigger_seq = s_event.trigger_seq,
                .event_post_count = s_event.post_count,
                .event_early_rejected = s_event.early_rejected,
                .event_busy_rejected = s_event.busy_rejected,
            };
            if (xQueueSend(s_diag_queue, &d, 0) != pdTRUE) {
                s_dropped_diagnostics++;
            }
            window_start_us = now_us;
            window_samples = 0U;
            window_bmp_reads = 0U;
            gap_min_us = INT64_MAX;
            gap_max_us = 0;
            gap_sum_us = 0;
            gap_count = 0U;
            gap_short_count = 0U;
            gap_long_count = 0U;
        }
    }
}

static void free_event_buffers(void)
{
    heap_caps_free(s_ring_a.storage);
    heap_caps_free(s_ring_b.storage);
    heap_caps_free(s_post_storage);
    memset(&s_ring_a, 0, sizeof(s_ring_a));
    memset(&s_ring_b, 0, sizeof(s_ring_b));
    memset(&s_event, 0, sizeof(s_event));
    s_post_storage = NULL;
    s_active_ring = NULL;
}

esp_err_t sensor_manager_start(struct bmi2_dev *bmi, struct bmp3_dev *bmp)
{
    if (bmi == NULL || bmp == NULL) return ESP_ERR_INVALID_ARG;
    if (s_task != NULL || s_timer != NULL || s_logger_task != NULL ||
        s_diag_queue != NULL || s_active_ring != NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    const size_t ring_bytes = (size_t)SENSOR_RING_CAPACITY * sizeof(sensor_sample_t);
    const size_t post_bytes = (size_t)SENSOR_POST_SAMPLES * sizeof(sensor_sample_t);
    size_t free_before = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    sensor_sample_t *a = heap_caps_calloc(SENSOR_RING_CAPACITY,
        sizeof(sensor_sample_t), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    sensor_sample_t *b = heap_caps_calloc(SENSOR_RING_CAPACITY,
        sizeof(sensor_sample_t), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    s_post_storage = heap_caps_calloc(SENSOR_POST_SAMPLES,
        sizeof(sensor_sample_t), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);

    if (a == NULL || b == NULL || s_post_storage == NULL) {
        ESP_LOGE(TAG, "PSRAM event alloc FAILED: requested=%u bytes free_before=%u",
                 (unsigned)(2U * ring_bytes + post_bytes), (unsigned)free_before);
        heap_caps_free(a);
        heap_caps_free(b);
        heap_caps_free(s_post_storage);
        s_post_storage = NULL;
        return ESP_ERR_NO_MEM;
    }
    (void)sensor_ring_init(&s_ring_a, a, SENSOR_RING_CAPACITY);
    (void)sensor_ring_init(&s_ring_b, b, SENSOR_RING_CAPACITY);
    s_active_ring = &s_ring_a;
    memset(&s_event, 0, sizeof(s_event));

    ESP_LOGI(TAG,
        "PSRAM event buffers allocated: rings=2x%u post=%u total=%u bytes; "
        "PSRAM free before=%u after=%u",
        (unsigned)ring_bytes, (unsigned)post_bytes,
        (unsigned)(2U * ring_bytes + post_bytes),
        (unsigned)free_before,
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));

    s_bmi = bmi;
    s_bmp = bmp;
    s_dropped_diagnostics = 0U;
    s_diag_queue = xQueueCreate(DIAG_QUEUE_LENGTH, sizeof(diag_snapshot_t));
    if (s_diag_queue == NULL) {
        free_event_buffers();
        return ESP_ERR_NO_MEM;
    }

    BaseType_t ret = xTaskCreate(logger_task, "sensor_log", LOGGER_TASK_STACK_BYTES,
                                 NULL, LOGGER_TASK_PRIORITY, &s_logger_task);
    if (ret != pdPASS) {
        s_logger_task = NULL;
        vQueueDelete(s_diag_queue);
        s_diag_queue = NULL;
        free_event_buffers();
        return ESP_ERR_NO_MEM;
    }
    ret = xTaskCreate(sensor_task, "sensor_task", SENSOR_TASK_STACK_BYTES,
                      NULL, SENSOR_TASK_PRIORITY, &s_task);
    if (ret != pdPASS) {
        s_task = NULL;
        vTaskDelete(s_logger_task);
        s_logger_task = NULL;
        vQueueDelete(s_diag_queue);
        s_diag_queue = NULL;
        free_event_buffers();
        return ESP_ERR_NO_MEM;
    }

    const esp_timer_create_args_t args = {
        .callback = &sensor_tick_cb,
        .arg = NULL,
        .dispatch_method = ESP_TIMER_TASK,
        .name = "imu_100hz",
    };
    esp_err_t err = esp_timer_create(&args, &s_timer);
    if (err != ESP_OK) goto fail;
    err = esp_timer_start_periodic(s_timer, SENSOR_PERIOD_US);
    if (err != ESP_OK) goto fail;

    ESP_LOGI(TAG, "esp_timer started: period=%u us; BMP3 every 4 ticks; logger task split",
             (unsigned)SENSOR_PERIOD_US);
    return ESP_OK;

fail:
    if (s_timer != NULL) {
        esp_timer_delete(s_timer);
        s_timer = NULL;
    }
    vTaskDelete(s_task);
    s_task = NULL;
    vTaskDelete(s_logger_task);
    s_logger_task = NULL;
    vQueueDelete(s_diag_queue);
    s_diag_queue = NULL;
    free_event_buffers();
    return err;
}
