"""Hardware-only Phase 4 test: captures ESP32 serial and demo broker publications.

Requires pyserial, Docker broker prepared by start_phase3_broker.ps1, and a
firmware built with local NETWORK_TEST_ALERT_SERIAL_ENABLED=1. Resets the board
once, sends local test input, and stops/starts ONLY fall-phase3-broker. No mock,
MQTT command, actuator control or Backend action. Credentials are never printed.
"""
import argparse
import hashlib
import json
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path

import serial

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = 'fall-phase3-broker'

def run_client(arguments, **kwargs):
    """TimeoutExpired normally renders argv, including the private password."""
    try:
        return subprocess.run(arguments, **kwargs)
    except (subprocess.TimeoutExpired, OSError):
        raise RuntimeError('MQTT test client failed or timed out; credentials omitted') from None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='COM5')
    parser.add_argument('--out-dir', type=Path, default=ROOT / 'build/phase8_2_4/hardware')
    args = parser.parse_args()
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    log = out / 'runtime.log'
    if log.exists():
        raise RuntimeError('Capture already exists; select a new --out-dir')
    secrets = json.loads((ROOT / 'build/phase8_2_3/broker/client_secrets.json').read_text())
    base = 'iot/devices/' + secrets['deviceId']
    auth = ['-u', secrets['backendUsername'], '-P', secrets['backendPassword']]
    frames, raw, errors = [], bytearray(), []
    done = threading.Event()
    started = time.monotonic()
    subscriber = None
    broker_stopped = False
    port = serial.Serial(port=None, baudrate=115200, timeout=0.2)
    port.dtr = port.rts = False
    port.port = args.port

    def capture():
        try:
            with log.open('xb') as handle:
                while not done.is_set():
                    data = port.read(min(max(port.in_waiting, 1), 8192))
                    raw.extend(data)
                    handle.write(data)
                    handle.flush()
        except Exception:
            errors.append('Serial capture failed')

    def start_subscriber():
        client_id = 'phase4-probe-' + uuid.uuid4().hex
        pid_file = '/tmp/' + client_id + '.pid'
        process = subprocess.Popen(['docker', 'exec', CONTAINER, 'sh', '-c',
                                    'echo $$ > "$1"; shift; exec "$@"', 'phase4', pid_file,
                                    'mosquitto_sub', '-h', '127.0.0.1', '-i', client_id, '-W', '180',
                                    *auth, '-t', base + '/status', '-t', base + '/event', '-q', '1',
                                    '-F', '%r %q %t %p'], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding='utf-8')
        def reader():
            for line in process.stdout:
                try:
                    retained, qos, topic, payload = line.strip().split(' ', 3)
                    frames.append(dict(elapsed_s=round(time.monotonic()-started, 3),
                                       retain=int(retained), qos=int(qos), topic=topic,
                                       payload=json.loads(payload)))
                except (ValueError, json.JSONDecodeError):
                    errors.append('Subscriber returned invalid JSON/format')
        threading.Thread(target=reader, daemon=True).start()
        return process, pid_file, client_id

    def stop_subscriber(probe):
        process, pid_file, client_id = probe
        # Killing docker.exe alone can leave its exec process in the container.
        # Kill only our recorded PID after verifying the unique client ID.
        subprocess.run(['docker', 'exec', CONTAINER, 'sh', '-c',
                        'if test -r "$1"; then read -r p < "$1"; '
                        'if test -r "/proc/$p/cmdline" && grep -q "$2" "/proc/$p/cmdline"; '
                        'then kill -TERM "$p"; fi; rm -f "$1"; fi',
                        'phase4-cleanup', pid_file, client_id], capture_output=True, timeout=10)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.terminate()

    def text():
        return re.sub(r'\x1b\[[0-9;]*m', '', bytes(raw).decode('utf-8', 'replace'))

    def wait_for(predicate, seconds, label):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if errors:
                raise RuntimeError(errors[0])
            if any(s in text() for s in ['Guru Meditation', 'panic_abort', 'assert failed', 'Brownout detector']):
                raise RuntimeError('Fatal firmware log detected')
            if predicate():
                print(label + ': PASS', flush=True)
                return
            time.sleep(0.2)
        raise RuntimeError(label + ': timed out; inspect runtime and broker logs')

    def observe(seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if errors:
                raise RuntimeError(errors[0])
            time.sleep(0.2)

    def events():
        return [f for f in frames if f['topic'] == base + '/event']

    def docker_action(action):
        r = subprocess.run(['docker', action, CONTAINER], capture_output=True, timeout=20)
        if r.returncode:
            raise RuntimeError('Docker broker ' + action + ' failed')

    try:
        port.open()
        subscriber = start_subscriber()
        capture_thread = threading.Thread(target=capture, daemon=True)
        capture_thread.start()
        observe(1)
        port.rts = True
        time.sleep(0.1)
        port.rts = False
        wait_for(lambda: 'SUBACK confirmed:' in text() and any(
            f['topic'] == base+'/status' and f['retain'] == 0 and f['payload'].get('online') is True
            for f in frames), 30, 'Boot: ESP32 online status + SUBACK')
        wait_for(lambda: time.monotonic()-started >= 13, 20, 'Startup observation')
        assert not events(), 'Unexpected event at boot'
        port.write(b'BAD\nTEST_ALERT extra\n')
        observe(1)
        assert not events(), 'Invalid serial input created an event'
        port.write(b'TEST_ALERT\n')
        wait_for(lambda: len(events()) == 1, 10, 'First controlled TEST_ALERT')
        port.write(b'TEST_ALERT\r\nTEST_ALERT\n')
        observe(2)
        assert len(events()) == 1, 'Cooldown did not suppress burst'
        observe(4)
        port.write(b'TEST_ALERT\n')
        wait_for(lambda: len(events()) == 2, 10, 'Second controlled TEST_ALERT')
        assert events()[0]['payload']['eventId'] != events()[1]['payload']['eventId']
        # Check before restart: persistence=false would otherwise clear even an
        # incorrectly retained event and make this test inconclusive.
        r = run_client(['docker', 'exec', CONTAINER, 'mosquitto_sub', '-h', '127.0.0.1',
                            *auth, '-t', base+'/event', '-q', '1', '-C', '1', '-W', '2'],
                           capture_output=True, text=True, timeout=7)
        assert not r.stdout.strip() and r.returncode != 0, 'Event unexpectedly retained'
        stop_subscriber(subscriber)
        subscriber = None
        # A request while offline is rejected; it must not be replayed on recovery.
        docker_action('stop')
        broker_stopped = True
        wait_for(lambda: 'MQTT_MANAGER: disconnected;' in text(), 20, 'Broker offline detected')
        port.write(b'TEST_ALERT\n')
        observe(12)
        docker_action('start')
        broker_stopped = False
        subscriber = start_subscriber()
        wait_for(lambda: text().count('SUBACK confirmed:') >= 2 and any(
            f['topic'] == base+'/status' and f['retain'] == 0 and f['payload'].get('online') is True
            and f['elapsed_s'] > 30 for f in frames), 30, 'Reconnect: fresh online status')
        observe(12)
        assert len(events()) == 2, 'Reconnect/offline request generated an extra event'
        r = run_client(['docker', 'exec', CONTAINER, 'mosquitto_sub', '-h', '127.0.0.1',
                            *auth, '-t', base+'/status', '-q', '1', '-C', '1', '-W', '5', '-F', '%r %q %p'],
                           capture_output=True, text=True, timeout=10)
        assert r.returncode == 0, 'Retained status read failed'
        retained, qos, payload = r.stdout.strip().split(' ', 2)
        assert retained == '1' and qos == '1' and json.loads(payload)['online'] is True
        (out / 'retained_status.json').write_text(json.dumps(json.loads(payload), indent=2))
        wait_for(lambda: 'CSV_EXPORT_FINISHED' in text(), 100, 'CSV completed with network activity')
        observe(10)
        for f in frames:
            p = f['payload']
            assert p['schemaVersion'] == 1 and p['deviceId'] == secrets['deviceId']
            assert f['qos'] == 1
            if f['topic'].endswith('/event'):
                assert f['retain'] == 0
                assert p['eventType'] == 'TEST_ALERT' and p['isTest'] is True
                assert str(uuid.UUID(p['eventId'], version=4)) == p['eventId']
                assert p['modelVersion'] == 'firmware-test-v1' and p['confidence'] is None
                assert p['location']['type'] in ['UNAVAILABLE', 'CURRENT', 'LAST_KNOWN']
                if p['location']['type'] == 'UNAVAILABLE':
                    assert all(p['location'][k] is None for k in ['lat', 'lon', 'observedAt'])
            else:
                assert p['mode'] == 'REAL' and p['lteReady'] is False
        diag = [l for l in text().splitlines() if 'SENSOR_MANAGER: diag_5s' in l]
        jitter = [l for l in text().splitlines() if 'SENSOR_MANAGER: diag_jitter' in l]
        assert len(diag) >= 12 and jitter
        for line in diag:
            assert 'imu_err=0' in line and 'missed_ticks=0' in line
        for line in jitter:
            assert all(k+'=0' in line for k in ['bmp_err', 'outliers', 'diag_dropped'])
        result = dict(phase='8.2.4', status='PASS', hardware_verified=True,
                      duration_s=round(time.monotonic()-started, 2),
                      events=len(events()), diag_windows=len(diag),
                      status_frames=sum(f['topic'].endswith('/status') for f in frames),
                      reconnect_no_extra_event=True, status_retained_online=True, event_retained=False)
        (out / 'results.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
    finally:
        done.set()
        if 'capture_thread' in locals():
            capture_thread.join(timeout=2)
        if port.is_open:
            port.close()
        if subscriber:
            stop_subscriber(subscriber)
        if broker_stopped:
            docker_action('start')
        (out / 'mqtt_frames.json').write_text(json.dumps(frames, indent=2))
        if log.exists():
            (out / 'runtime.sha256').write_text(hashlib.sha256(log.read_bytes()).hexdigest())

if __name__ == '__main__':
    main()
