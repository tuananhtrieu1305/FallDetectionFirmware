"""Check a closed real-board MQTT capture. Never certify Backend/App E2E.

Consumes the shared phase6 recorder format (optionally --observe-command).
No network calls, command publication, mock, credentials or Backend API guesses.
"""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re


def utc(value):
    if value is None:
        return True
    if not isinstance(value, str) or not re.fullmatch(r'20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ', value):
        return False
    try:
        datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
        return True
    except ValueError:
        return False


def location(value):
    if not isinstance(value, dict) or not {'type', 'lat', 'lon', 'observedAt'} <= value.keys():
        return False
    if value['type'] == 'UNAVAILABLE':
        return all(value[k] is None for k in ['lat', 'lon', 'observedAt'])
    return (value['type'] in ['CURRENT', 'LAST_KNOWN'] and utc(value['observedAt']) and
            all(type(value[k]) in [float, int] and math.isfinite(value[k]) and abs(value[k]) <= bound
                for k, bound in [('lat', 90), ('lon', 180)]))


def evaluate(summary, raw, frames, device):
    text = raw.decode('utf-8', errors='replace')
    base = 'iot/devices/' + device
    frames = [f for f in frames if isinstance(f, dict) and isinstance(f.get('payload'), dict)]

    def live(f):
        return f.get('qos') == 1 and f.get('retain') == 0

    def envelope(p):
        return type(p.get('schemaVersion')) is int and p['schemaVersion'] == 1 and p.get('deviceId') == device

    healthy = (summary.get('raw_sha256') == hashlib.sha256(raw).hexdigest() and
               summary.get('reset_count') == 1 and summary.get('fatal') is False and
               summary.get('collector_errors') == [] and summary.get('diag_windows', 0) > 0 and
               all(summary.get(k) == 0 for k in ['missed_ticks_max', 'imu_err_max', 'bmp_err_max',
                                                'outliers_max', 'diag_dropped_max']))
    boot = bool(re.search(r'ELF file SHA256:\s+[0-9a-f]{9,}', text)) and 'SUBACK confirmed:' in text
    statuses = [f for f in frames if f.get('topic') == base + '/status']
    real = any(live(f) and envelope(p := f['payload']) and p.get('online') is True and
               p.get('mode') == 'REAL' and p.get('lteReady') is False and
               p.get('alertState') in ['IDLE', 'BUZZER_ON', None] and 'observedAt' in p and utc(p['observedAt'])
               for f in statuses)
    events = [f for f in frames if f.get('topic') == base + '/event']

    def event_valid(f):
        p = f['payload']
        return (live(f) and envelope(p) and p.get('eventType') == 'TEST_ALERT' and p.get('isTest') is True and
                isinstance(p.get('eventId'), str) and bool(re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', p['eventId'])) and
                'occurredAt' in p and utc(p['occurredAt']) and p.get('modelVersion') == 'firmware-test-v1' and
                'confidence' in p and p['confidence'] is None and location(p.get('location')) and
                f"TEST_ALERT requested: eventId={p['eventId']} isTest=true" in text)

    event_ok = bool(events) and all(event_valid(f) for f in events)
    commands = [f for f in frames if f.get('topic') == base + '/command']
    executed = []
    if healthy and boot and real and event_ok:
        for frame in commands:
            c = frame['payload']
            if not (live(frame) and set(c) == {'commandId', 'eventId', 'command', 'issuedAt'} and
                    all(isinstance(x, str) for x in c.values()) and c['command'] == 'STOP_BUZZER' and
                    re.fullmatch(r'[A-Za-z0-9_-]{1,64}', c['commandId']) and utc(c['issuedAt']) and
                    c['eventId'] in {f['payload']['eventId'] for f in events}):
                continue
            marker = f"STOP_BUZZER EXECUTED commandId={c['commandId']} eventId={c['eventId']}; output verified off; event retained"
            for status in statuses:
                p = status['payload']; ack = p.get('lastCommand', {})
                if not isinstance(ack, dict):
                    continue
                if (live(status) and envelope(p) and p.get('mode') == 'REAL' and p.get('alertState') == 'IDLE' and
                        all(ack.get(k) == c[k] for k in ['commandId', 'eventId', 'command']) and
                        ack.get('result') == 'EXECUTED' and ack.get('reason') == 'STOPPED' and
                        isinstance(ack.get('processedAt'), str) and utc(ack['processedAt']) and marker in text):
                    executed.append(dict(commandId=c['commandId'], eventId=c['eventId'], processedAt=ack['processedAt']))
                    break
    return dict(device_to_broker='PASS' if healthy and boot and real and event_ok else 'INCOMPLETE_OR_FAILED',
                checks=dict(closed_hash_and_sensor_health=healthy, serial_boot_and_suback=boot,
                            fresh_real_status=real, safe_test_events_from_local_serial=event_ok),
                event_deliveries=len(events), unique_event_ids=sorted({f['payload']['eventId'] for f in events if event_valid(f)}),
                observed_command_frames=len(commands), correlated_executions=executed,
                command_device_ack='PASS' if executed else 'INCOMPLETE_OR_FAILED' if commands else 'NOT_OBSERVED',
                command_publisher_identity='NOT_VERIFIED', backend_receive='NOT_VERIFIED',
                backend_persistence='NOT_VERIFIED', app_notification='NOT_VERIFIED',
                app_via_backend_command='NOT_VERIFIED', backend_app_ack='NOT_VERIFIED', end_to_end='NOT_VERIFIED')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture_dir', type=Path)
    p.add_argument('--device-id', default='waist-esp32s3-001')
    p.add_argument('--require-command', action='store_true', help='Also require an observed command + real execution ACK')
    a = p.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,48}', a.device_id):
        print('Invalid device ID')
        return 2
    try:
        summary = json.loads((a.capture_dir / 'status.json').read_text())
        raw = (a.capture_dir / 'runtime.log').read_bytes()
        frames = json.loads((a.capture_dir / 'mqtt_frames.json').read_text())
        if not isinstance(summary, dict) or not isinstance(frames, list):
            raise ValueError('Invalid capture structure')
        report = evaluate(summary, raw, frames, a.device_id)
        (a.capture_dir / 'phase7_broker_leg.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    except (OSError, ValueError, TypeError):
        print('INCOMPLETE: closed capture files missing or invalid; no E2E verdict')
        return 1
    print(json.dumps(report, indent=2))
    return 0 if report['device_to_broker'] == 'PASS' and (not a.require_command or report['command_device_ack'] == 'PASS') else 1


if __name__ == '__main__':
    raise SystemExit(main())
