#pragma once
#include <stdint.h>

#define SENSOR_IMU_HZ 100U
#define SENSOR_PRESSURE_HZ 25U
#define SENSOR_PERIOD_US 10000U
#define SENSOR_PRE_SAMPLES 3000U
#define SENSOR_POST_SAMPLES 1000U
#define SENSOR_RING_CAPACITY (SENSOR_PRE_SAMPLES + SENSOR_POST_SAMPLES)
#define SENSOR_FLAG_PRESSURE_VALID 0x01U
#define SENSOR_FLAG_EVENT_MARKER   0x02U

typedef struct {
    int64_t timestamp_us;           // Host monotonic timestamp immediately before BMI270 I2C read
    float ax, ay, az;               // Sensor axes, m/s^2; gravity INCLUDED
    float gx, gy, gz;               // Sensor axes, rad/s
    float pressure_pa;              // Last valid, non-future BMP3 pressure; ignored if flag unset
    uint32_t seq;                   // IMU scheduled tick index; missing ticks produce gaps
    uint32_t flags;                 // Bitmask: 0x01 pressure valid, 0x02 button event marker
    int64_t pressure_timestamp_us;  // Host monotonic BMP3 READ time; 0 when invalid
} sensor_sample_t;
