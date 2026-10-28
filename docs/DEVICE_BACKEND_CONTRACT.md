# Device ↔ Backend Contract — sensor-v1 / mqtt-v1

Status: PHASE 8.1 development contract.

LTE hardware is NOT READY. Backend/App/Web development
can proceed using the MQTT mock device.

## 1. Transport and Topics

Development broker: Mosquitto.

Local development:

- Host: localhost
- Port: 1883

Production:

- Authenticated MQTT
- TLS
- Per-device authorization

Example device ID:

`waist-esp32s3-001`

| Topic                             | Publisher   | Subscriber  | QoS | Retain |
| --------------------------------- | ----------- | ----------- | --- | ------ |
| `iot/devices/{deviceId}/event`    | Device/Mock | Backend     | 1   | No     |
| `iot/devices/{deviceId}/status`   | Device/Mock | Backend     | 1   | Yes    |
| `iot/devices/{deviceId}/location` | Device      | Backend     | 1   | No     |
| `iot/devices/{deviceId}/command`  | Backend     | Device/Mock | 1   | No     |
| `iot/devices/{deviceId}/health`   | Device      | Backend     | 0   | No     |

`diagnostic/window` is used for firmware debugging only.

It is not required for App/Web integration.

During Phase 8.1, the mock implements event, status
and command. Independent location and health publications
are not implemented yet.

## 2. Event Payload

Example of a confirmed fall event:

```json
{
  "schemaVersion": 1,
  "eventId": "f3be2ca6-c8fa-4ab5-aae6-b94cab0398c1",
  "deviceId": "waist-esp32s3-001",
  "eventType": "FALL_CONFIRMED",
  "isTest": false,
  "occurredAt": "2026-10-27T13:00:00Z",
  "modelVersion": "fall-ai-v1",
  "confidence": 0.93,
  "location": {
    "type": "LAST_KNOWN",
    "lat": 21.0,
    "lon": 105.8,
    "observedAt": "2026-10-27T12:58:00Z"
  }
}
```

The coordinates above are illustrative and are not
actual readings from the device.

### Field Semantics

- `schemaVersion`: MQTT contract version.
- `eventId`: Unique event identifier.
- `deviceId`: Device identifier.
- `eventType`: Event type.
- `isTest`: Whether the event is synthetic/test-only.
- `occurredAt`: Event time in UTC RFC3339 format.
- `modelVersion`: AI model version.
- `confidence`: Value from 0 to 1, or null.
- `location`: Current, last-known, or unavailable position.

Location types:

- `CURRENT`
- `LAST_KNOWN`
- `UNAVAILABLE`

When location is UNAVAILABLE:

- `lat = null`
- `lon = null`
- `observedAt = null`

If the device cannot determine UTC time,
`occurredAt` must be null.

The backend must independently record server reception time.

### Event Safety Rules

Only:

`eventType = FALL_CONFIRMED`

with:

`isTest = false`

is eligible for the real emergency workflow.

A test event uses:

`eventType = TEST_ALERT`

and:

`isTest = true`

Test events MUST NOT trigger real emergency calls,
SMS escalation, or external emergency services.

The backend must prevent duplicate alerts using
the unique pair:

`(deviceId, eventId)`

## 3. Status Payload

Example:

```json
{
  "schemaVersion": 1,
  "deviceId": "waist-esp32s3-001",
  "online": true,
  "mode": "MOCK",
  "lteReady": false,
  "alertState": "BUZZER_ON",
  "observedAt": "2026-10-27T13:00:00Z"
}
```

### Device Modes

- `MOCK`: Python simulator.
- `REAL`: Actual wearable device.

MOCK online does NOT mean the wearable is online.

The backend must distinguish simulator status
from actual hardware status.

The current LTE connection is unverified.

Use MQTT Last Will to publish:

`online = false`

when a client disconnects unexpectedly.

Only status messages should be retained.

Events and commands must not be retained.

Do not run the mock and real device simultaneously
with the same device ID.

## 4. Command Payload

Topic:

`iot/devices/{deviceId}/command`

Example:

```json
{
  "commandId": "b4faf61c-4ae4-4655-b3dc-496bb8b17e36",
  "eventId": "f3be2ca6-c8fa-4ab5-aae6-b94cab0398c1",
  "command": "STOP_BUZZER",
  "issuedAt": "2026-10-27T13:00:30Z"
}
```

### STOP_BUZZER

The backend sends STOP_BUZZER when an authorized
user requests that the wearable stop sounding
its local buzzer.

The device must validate:

- Command authorization.
- Matching eventId.
- Command expiration.
- Duplicate commandId.
- Current alert state.

The real device must acknowledge execution separately.

MQTT publication alone is NOT proof that the buzzer stopped.

### Mock Acknowledgement

The mock changes its simulated alertState to IDLE.

It publishes status containing:

```json
{
  "lastCommand": {
    "commandId": "b4faf61c-4ae4-4655-b3dc-496bb8b17e36",
    "command": "STOP_BUZZER",
    "result": "ACK_SIMULATED",
    "processedAt": "2026-10-27T13:00:31Z"
  }
}
```

ACK_SIMULATED is only a simulator acknowledgement.

It must never be presented as confirmation
that physical ESP32 hardware has executed the command.

## 5. Backend Responsibilities

### MQTT

- Subscribe to device events.
- Subscribe to device status.
- Validate message schema.
- Verify device identity.
- Handle reconnects and duplicate deliveries.

### Persistence

Use PostgreSQL to store:

- Devices.
- Users.
- Caregivers.
- Fall events.
- Alert status.
- Acknowledgements.
- Location snapshots.

Prevent duplicate alerts using:

`UNIQUE(deviceId, eventId)`

### App/Web Delivery

Spring Boot provides:

- REST API.
- WebSocket.
- FCM/push integration.

Android and Web must NOT directly subscribe
to the device MQTT broker.

### Command Routing

Android/Web requests are sent to Spring Boot.

Spring Boot authenticates and authorizes requests.

Spring Boot then publishes MQTT commands.

## 6. Current Integration Limitations

### A7670C LTE

- AT command response observed.
- SIM recognition observed.
- UART communication has been unstable.
- LTE registration/APN/IP/MQTT are NOT PASS.

The LTE firmware remains offline-safe.

### GNSS

- NMEA parser tested.
- Last Known Location logic implemented.
- Outdoor fix remains to be confirmed.

### AI

- Sensor acquisition and logging implemented.
- Real on-device AI fall inference is not yet complete.

### Mock Device

`tools/mock_device.py` is a development simulator.

It runs on a computer.

Successful mock MQTT communication is NOT proof
of successful LTE communication from ESP32.

## 7. Integration Acceptance Criteria

1. Mock connects to Mosquitto.
2. Backend receives TEST_ALERT.
3. Backend validates schemaVersion and isTest.
4. Backend stores the event without duplication.
5. Android/Web displays a test alert.
6. Authorized user requests STOP_BUZZER.
7. Backend publishes the MQTT command.
8. Mock returns ACK_SIMULATED.
9. Backend/UI displays simulated acknowledgement.
10. No real emergency escalation occurs.

## 8. Versioning

Current contract:

`mqtt-v1`

Changes to topics, required payload fields, or command
semantics must be agreed upon by Firmware and App/Web
members before implementation.
