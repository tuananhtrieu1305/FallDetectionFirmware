
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "sensor_sample.h"

/*
 * PHASE 5.5a: Single-writer rolling RAM ring.
 *
 * Only sensor_task may call init/append/stats.
 * No concurrent reader yet.
 *
 * An overwrite means an OLD sample was evicted
 * when the 40-second ring is full.
 * It does NOT mean an IMU tick was missed.
 *
 * Event freeze, 30s pre + 10s post capture,
 * and CSV are implemented in later steps.
 */

typedef struct {
    sensor_sample_t *storage;
    uint32_t capacity;
    uint32_t head;
    uint32_t count;
    uint32_t last_seq;
    uint64_t total_written;
    uint64_t evicted_oldest;
} sensor_ring_t;

static inline bool sensor_ring_init(
    sensor_ring_t *r,
    sensor_sample_t *storage,
    uint32_t capacity)
{
    if (r == NULL || storage == NULL || capacity == 0U) {
        return false;
    }

    *r = (sensor_ring_t){
        .storage = storage,
        .capacity = capacity,
    };

    return true;
}

static inline void sensor_ring_append(
    sensor_ring_t *r,
    const sensor_sample_t *sample)
{
    /* Precondition: initialized ring, single writer. */

    r->storage[r->head] = *sample;

    r->head++;

    if (r->head == r->capacity) {
        r->head = 0U;
    }

    if (r->count < r->capacity) {
        r->count++;
    } else {
        r->evicted_oldest++;
    }

    r->total_written++;
    r->last_seq = sample->seq;
}

static inline uint32_t sensor_ring_oldest_index(
    const sensor_ring_t *r)
{
    return (r->head + r->capacity - r->count)
           % r->capacity;
}
