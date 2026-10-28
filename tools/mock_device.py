"""Phase 8 development-only MQTT mock.

No A7670C or ESP32 required.
Never use test events for real emergency escalation.
"""

import argparse
import json
import os
import threading
import time
import uuid
from datetime import UTC, datetime

import paho.mqtt.client as mqtt


def utc_now():
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def encode(obj):
    return json.dumps(
        obj,
        ensure_ascii=False,
        separators=(",", ":"),
    )


class MockDevice:
    def __init__(self, broker, port, device_id):
        self.device_id = device_id
        self.event_id = str(uuid.uuid4())

        self.connected = threading.Event()
        self.buzzer_on = False
        self.last_command = None

        self.base = f"iot/devices/{device_id}"

        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"mock-{device_id}-{uuid.uuid4().hex[:8]}",
        )

        username = os.getenv("MQTT_USERNAME")

        if username:
            self.client.username_pw_set(
                username,
                os.getenv("MQTT_PASSWORD", ""),
            )

        # MQTT Last Will: simulated device offline.
        self.client.will_set(
            f"{self.base}/status",
            encode(self.status(False)),
            qos=1,
            retain=True,
        )

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

        self.broker = broker
        self.port = port

    def status(self, online):
        result = {
            "schemaVersion": 1,
            "deviceId": self.device_id,
            "online": online,
            "mode": "MOCK",
            "lteReady": False,
            "alertState": ("BUZZER_ON" if self.buzzer_on else "IDLE"),
            "observedAt": utc_now(),
        }

        if self.last_command:
            result["lastCommand"] = self.last_command

        return result

    def publish_status(self, online):
        self.client.publish(
            f"{self.base}/status",
            encode(self.status(online)),
            qos=1,
            retain=True,
        )

    def on_connect(
        self,
        client,
        userdata,
        flags,
        reason_code,
        properties,
    ):
        if reason_code.is_failure:
            print(f"MQTT connect rejected: {reason_code}")
            return

        client.subscribe(
            f"{self.base}/command",
            qos=1,
        )

        self.connected.set()
        self.publish_status(True)

        print(f"CONNECTED: {self.base} (MOCK mode)")

    def on_disconnect(
        self,
        client,
        userdata,
        disconnect_flags,
        reason_code,
        properties,
    ):
        self.connected.clear()
        print(f"MQTT disconnected: {reason_code}")

    def on_message(
        self,
        client,
        userdata,
        message,
    ):
        try:
            cmd = json.loads(message.payload.decode("utf-8"))

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            print("IGNORED malformed command")
            return

        if not isinstance(cmd, dict):
            print("IGNORED non-object command")
            return

        if cmd.get("command") != "STOP_BUZZER":
            print("IGNORED unsupported command")
            return

        if cmd.get("eventId") != self.event_id:
            print("IGNORED command for another event")
            return

        command_id = cmd.get("commandId")

        if not isinstance(command_id, str) or not command_id:
            print("IGNORED command without commandId")
            return

        # Simulate stopping the buzzer.
        # This does NOT control ESP32 hardware.
        self.buzzer_on = False

        self.last_command = {
            "commandId": command_id,
            "command": "STOP_BUZZER",
            "result": "ACK_SIMULATED",
            "processedAt": utc_now(),
        }

        self.publish_status(True)

        print("STOP_BUZZER simulated; " "status updated (no hardware buzzer)")

    def publish_test_event(self):
        self.buzzer_on = True
        self.publish_status(True)

        event = {
            "schemaVersion": 1,
            "eventId": self.event_id,
            "deviceId": self.device_id,
            "eventType": "TEST_ALERT",
            "isTest": True,
            "occurredAt": utc_now(),
            "modelVersion": "mock-v1",
            "confidence": None,
            "location": {
                "type": "UNAVAILABLE",
                "lat": None,
                "lon": None,
                "observedAt": None,
            },
        }

        info = self.client.publish(
            f"{self.base}/event",
            encode(event),
            qos=1,
            retain=False,
        )

        info.wait_for_publish(timeout=5)

        if not info.is_published():
            raise RuntimeError("TEST_ALERT was not published")

        print(f"TEST_ALERT sent, eventId={self.event_id}")

        print(
            "This is synthetic; never dispatch "
            "emergency notifications from isTest=true"
        )

    def run(self):
        self.client.connect(
            self.broker,
            self.port,
            keepalive=60,
        )

        self.client.loop_start()

        try:
            if not self.connected.wait(timeout=10):
                raise RuntimeError("MQTT broker did not accept the connection")

            self.publish_test_event()

            while True:
                time.sleep(10)

                if self.connected.is_set():
                    self.publish_status(True)

        except KeyboardInterrupt:
            print("Stopping mock device")

        finally:
            if self.connected.is_set():
                self.publish_status(False)
                time.sleep(0.3)

            self.client.disconnect()
            self.client.loop_stop()


def main():
    parser = argparse.ArgumentParser(description="Test MQTT device for App/Web")

    parser.add_argument(
        "--broker",
        default="127.0.0.1",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=1883,
    )

    parser.add_argument(
        "--device-id",
        default="waist-esp32s3-001",
    )

    args = parser.parse_args()

    MockDevice(
        args.broker,
        args.port,
        args.device_id,
    ).run()


if __name__ == "__main__":
    main()
