#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "mqtt_manager.h"

/* Single owner: telemetry worker. No calls from callbacks/ISR/other tasks.
 * Demo profile requires explicit local enable; no production authorization.
 */
void command_processor_init(bool enabled);
bool command_processor_enabled(void);
esp_err_t command_processor_arm_test(const char *event_id, int64_t monotonic_us);
void command_processor_tick(int64_t monotonic_us);
void command_processor_process(const mqtt_manager_command_t *frame, uint32_t current_epoch, int64_t utc_ms);
bool command_processor_ack_pending(void);
void command_processor_ack_queued(void);
size_t command_processor_ack_json(char *out, size_t capacity);
