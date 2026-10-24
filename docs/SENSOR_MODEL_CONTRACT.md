# SENSOR MODEL CONTRACT — Hardware ↔ AI/Data

**Contract**: sensor-v1 / Phase 5 (2026-10-23)
**Placement**: waist / abdomen (eo–bụng).
**Status (2026-10-23)**: Hardware/Firmware **approved step 5.1**. AI/Data review pending before labeled dataset collection. **NOT an AI model input contract**.

## 1. Agreement table

| Property                     | Contract                                                                             | Important caveat                                                                         |
| ---------------------------- | ------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| Primary sensor               | BMI270 accelerometer + gyroscope                                                     | Bosch SensorAPI; configured 100 Hz for BOTH accel/gyro                                   |
| Primary output cadence       | Nominal **100 Hz** (one host read request every 10,000 µs)                           | This is requested polling cadence, NOT proof that every physical conversion was captured |
| BMI270 range                 | Accelerometer ±8 g, gyroscope ±2000 dps                                              | Must match runtime config for raw-to-SI conversion                                       |
| Supplemental pressure sensor | Actual identified **BMP388-compatible, chip ID 0x50**, I²C address 0x76              | Original shop listing BMP390/BMP390L; metadata must reflect actual detection             |
| Pressure acquisition         | Nominal 25 Hz, read after every 4th IMU slot                                         | Pressure hardware ODR must also be configured sufficiently high in existing init         |
| Acceleration                 | m/s², `ax`, `ay`, `az`; includes gravity (specific force)                            | NOT gravity-removed linear acceleration; no filtering                                    |
| Gyroscope                    | rad/s, `gx`, `gy`, `gz`                                                              | Angular velocity; NOT angles/orientation                                                 |
| Pressure                     | Pa, `pressure_pa` (absolute atmospheric pressure)                                    | NOT hPa, not altitude, not differential pressure                                         |
| Timestamp unit               | Signed 64-bit integer, µs                                                            | `esp_timer_get_time()`; monotonic since device boot; resets after reboot/deep sleep      |
| `timestamp_us` semantics     | Host timestamp **immediately before the BMI270 register-read call**                  | NOT guaranteed to equal the BMI270's hardware sampling/DRDY time                         |
| `pressure_timestamp_us`      | Host timestamp immediately after reading pressure, 0/missing if pressure unavailable | Last-read (past) pressure is copied to up to ~80 ms of subsequent IMU samples            |
| Ordering                     | Ascending `timestamp_us`, normally 10,000 µs apart                                   | Verify irregularities, never synthesize rows invisibly                                   |
| Missing data                 | Missing pressure fields are EMPTY, and `flags & 1 == 0`                              | Do NOT replace absent pressure with 0, interpolate or forward-fill without documentation |
| Missing IMU                  | No sample row emitted if IMU read fails; `seq` gap                                   | Counter increments for scheduled slots, including skipped and failed slots               |
| Frame                        | `sensor_frame_unmapped` by default                                                   | `ax..gz` are NOT asserted to be body-frame values yet                                    |
| Placement                    | `waist`                                                                              | Record orientation, belt position/side and wearer notes per session when known           |
| Optional MAX30102            | Separate stream/file, with its own rate, timing, and missingness                     | Does not gate or block the primary IMU sampling path                                     |

## 2. Body frame vs sensor frame

### Proposed right-handed BODY axes

- `+X_body`: points toward the **front** of the wearer.
- `+Y_body`: points toward the **wearer's LEFT**.
- `+Z_body`: points **up** toward the wearer's head.
- `X × Y = Z` (right-handed).

A **sensor/PCB frame** is the coordinate frame printed/defined by the BMI270 chip and determined by how its breakout PCB is soldered into the wearable. Turning the board on the belt changes the relation to the wearer's body.

**Do not silently assert that sensor axes are already BODY axes.** Phase 5 exports native chip axes as `sensor_frame_unmapped`. Once physical assembly and orientation are verified, record the explicit transformation `v_body = R_body_from_sensor · v_sensor` for **both** acceleration and gyro (plus orientation identifier). Use a proper signed axis permutation/rotation, not guessed signs. A test with known front/left/up motions is required. Gravity in a standing pose alone is insufficient to establish all 3 axes.

## 3. Exact CSV schema — `sensor-v1`

```csv
timestamp_us,ax,ay,az,gx,gy,gz,pressure_pa,seq,pressure_timestamp_us,flags
```

| Index | Column                  | Type                            | Meaning                                                                                       |
| ----- | ----------------------- | ------------------------------- | --------------------------------------------------------------------------------------------- |
| 1     | `timestamp_us`          | `int64`                         | Monotonic host time at start of IMU read, microseconds since boot                             |
| 2–4   | `ax,ay,az`              | `float32` serialized as decimal | Native sensor acceleration axes, **m/s²**                                                     |
| 5–7   | `gx,gy,gz`              | `float32` serialized as decimal | Native sensor gyro axes, **rad/s**                                                            |
| 8     | `pressure_pa`           | `float32` or blank              | Last pressure in **Pa**, only if fresh and valid                                              |
| 9     | `seq`                   | `uint32`                        | Counts scheduled IMU polling slots; starts near 1; gaps signal incomplete acquisition/logging |
| 10    | `pressure_timestamp_us` | `int64` or blank                | Monotonic host time when BMP3 was last read                                                   |
| 11    | `flags`                 | `uint32`                        | Bitmask: `0x01` pressure valid, `0x02` button event marker                                    |

**Minimum required field order remains exactly** `timestamp_us,ax,ay,az,gx,gy,gz,pressure_pa` with diagnostic fields appended. AI can ignore additional fields for a baseline, but must preserve them in raw dataset.

**Example only** (not actual measured data):

```csv
timestamp_us,ax,ay,az,gx,gy,gz,pressure_pa,seq,pressure_timestamp_us,flags
123450000,0.12,-9.76,0.11,0.001,-0.002,0.003,101320.82,1001,123430000,1
123460008,0.15,-9.74,0.09,0.002,-0.001,0.004,,1002,,0
```

Pressure missing is valid; acceleration near 9.8 m/s² at rest is expected, depending on orientation.

## 4. Timestamp integrity & sampling limitations

The initial version uses `esp_timer` (periodic 10,000 µs callback) to **notify** a high-priority FreeRTOS task. The task records time immediately before calling `bmi2_get_sensor_data`; callback does NO I²C, NO printf, NO malloc. `ulTaskNotifyTake()` counts delivered notifications and discards overdue ticks rather than inventing observations. The `seq` counter identifies missed software scheduling slots.

ESP Timer supports a microsecond monotonic host clock but does **not** timestamp BMI270's physical ADC conversion. With BMI270 INT/data-ready not connected, 100 Hz host polls can occasionally read the same hardware conversion twice or miss one; `seq` cannot detect this category of physical sample loss. For a later strict sensor-synchronous logger, wire BMI270 `INT1` to a spare ESP32-S3 GPIO, configure data-ready interrupt or FIFO + sensor time, capture a host timestamp at IRQ, and measure latency/drift. **Do not call current polling timestamps physically exact.**

`timestamp_us` is local to a session and not UTC. A UTC start-time offset can be stored separately (with source and uncertainty) if later available. Do NOT interleave sessions on `timestamp_us` alone.

## 5. Barometer alignment and missingness

- BMP3 read occurs **after** the current BMI270 row is captured/pushed.
- Next BMI270 rows inherit the latest **previous** pressure value. `pressure_timestamp_us <= timestamp_us` whenever `flags & 1` is true.
- If no pressure read has succeeded, or its host age exceeds **80 ms**, CSV pressure and pressure timestamp are blank; bit 0 cleared.
- Repeating a previous barometer value is **sample-and-hold**, not new 100 Hz pressure measurement. AI should deduplicate/filter pressure only when relevant, and always retain raw values/timestamps.
- A BMP3 successful API read does not itself prove a new 25 Hz physical conversion. Confirm operating mode/ODR with existing driver setup.

## 6. Session metadata (`*.metadata.json`)

Required per recording:

```json
{
  "schemaVersion": "sensor-v1",
  "deviceId": "<board-MAC>",
  "firmwareVersion": "phase5.0.0",
  "sensorModel": { "imu": "BMI270", "pressure": "BMP388_chip0x50" },
  "samplingRateHz": { "imu": 100, "pressure": 25 },
  "placement": "waist",
  "orientation": "sensor_frame_unmapped",
  "sessionId": "<device-and-run-id>",
  "timestampSemantics": "host_monotonic_pre_imu_read"
}
```

Before dataset collection, add an annotation manifest next to the recording with **wearer/pseudonym, attachment/rotation diagram or explicit rotation matrix (when verified), activity label, start/end mark times, environment, and test protocol**. These are **data collection annotations** and not firmware sensor field definitions. Do not store personal details inside the firmware printout.

## 7. Event ring buffer contract

- Sample struct contains `int64 timestamp`, 7 float measurements, `uint32 seq`, `uint32 flags`, `int64 pressure_timestamp` (typically **56 bytes with ESP32-S3 8-byte alignment**; use `sizeof(sensor_sample_t)` to verify).
- One circular ring of 4000 samples in PSRAM, nominally **40 seconds** total (30 s before + 10 s after event).
- Before event: new samples overwrite the oldest when full. After event: record 1000 _successful_ samples, then **freeze**.
- A GPIO4 active-low press marks the event **for Phase 5 hardware tests** only. It is NOT an authoritative label for the moment a real fall occurred and temporarily repurposes the button from alert-cancel usage.
- Continuous CSV logger continues independently after the ring freezes. The ring exists as a protected snapshot, but this starter implementation **does not yet export the frozen snapshot** as a second CSV (to avoid saturating live serial output).
- `sensor_ring_get()` only permits chronological access once frozen. Do not read while writer is modifying the ring.

## 8. Quality checks / Acceptance

Collect at least 5 minutes continuously with the board stationary, then move/tilt it and perform a safe button-mark test (not a real human fall).

1. Runtime confirms ACC/GYR ODR = 100 Hz, ranges ±8 g/±2000 dps; BMP3 pressure returns Pa.
2. Calculate observed IMU rows/elapsed time, median and p99 of `Δtimestamp_us` and gaps in `seq`.
3. **Targets for initial lab PASS:** median spacing near 10,000 µs; ≥99% observed intervals fall in 8,000–12,000 µs; missed software slots <0.1%; logger queue drops = 0; no timestamp regression; no malformed CSV rows. Targets are engineering gates, NOT guarantees.
4. Jitter and drops must be assessed separately; average rate ~100 Hz alone does NOT prove good scheduling.
5. Confirm 0–80 ms pressure age, data fields are SI, gravity present, orientation remains explicit.
6. Trigger ring; after 1000 successful later IMU rows, inspect `ring_frozen=1` and `ring_count=4000` if enough prehistory was collected. If not, smaller ring count is expected.
7. If the device sleeps/reboots or UART disconnects, start a new session rather than concatenating raw timestamps.

## 9. Outside the scope of Phase 5

- ML model architecture, feature windows, input shape, resampling to model rate, normalization strategy, on-device inference, FALL state machine, LTE/GNSS/MQTT.
- AI must NOT assume frame/window length, fall thresholds or inference features from this document.
- MAX30102 is optional. Its raw light/heart-rate streams, if added, have a separate sampling pipeline and separate schema, and never block IMU.

**Hardware & AI sign-off required on** sampling rate, units, timestamp semantics, axis/frame semantics, field order and missing data semantics **before collecting labeled training data**.
