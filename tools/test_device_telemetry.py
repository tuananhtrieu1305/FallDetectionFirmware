"""Host tests of real firmware publisher; fake SDK does not prove hardware PASS."""
import gzip
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ['encoders', 'status', 'reconnect', 'buzzer', 'event', 'retry',
             'giveup', 'offline', 'epoch', 'serial', 'overflow', 'binary',
             'gnss-error', 'task-fail', 'uart-fail', 'uart-owned', 'motor', 'offline-probe']

def main():
    build = ROOT / 'build/phase8_2_4/host_tests'
    include = build / 'include'
    for name in ['esp_err.h', 'esp_log.h', 'esp_timer.h', 'esp_random.h',
                 'driver/uart.h', 'freertos/FreeRTOS.h', 'freertos/task.h', 'esp_heap_caps.h', 'esp_netif.h']:
        p = include / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('#include "host_sdk.h"\n')
    cc = 'C:/msys64/ucrt64/bin/gcc.exe'
    obj = build / 'host_test.o'
    subprocess.run([cc, '-std=gnu17', '-Wall', '-Wextra', '-Werror', '--coverage',
                    '-I', str(include), '-I', str(ROOT / 'tests/device_telemetry'),
                    '-I', str(ROOT / 'main'), '-c', str(ROOT / 'tests/device_telemetry/host_test.c'), '-o', str(obj)], check=True)
    (build / 'host_test.gcda').unlink(missing_ok=True)
    exe = build / 'telemetry_tests.exe'
    subprocess.run([cc, '--coverage', str(obj), '-o', str(exe)], check=True)
    for name in SCENARIOS:
        r = subprocess.run([str(exe), name], capture_output=True, text=True, cwd=build)
        (build / (name + '.log')).write_text(r.stdout + r.stderr)
        assert r.returncode == 0, f'{name}: {r.stdout}{r.stderr}'
        for line in r.stdout.splitlines():
            if line.startswith('PAYLOAD '):
                _, channel, data = line.split(' ', 2)
                payload = json.loads(data)
                assert payload['schemaVersion'] == 1 and payload['deviceId'] == 'waist-esp32s3-001'
                if channel == '0':
                    assert payload['online'] is True and payload['mode'] == 'REAL' and payload['lteReady'] is False
                else:
                    import uuid
                    assert str(uuid.UUID(payload['eventId'], version=4)) == payload['eventId']
                    assert payload['isTest'] is True and payload['eventType'] == 'TEST_ALERT'
                    assert payload['confidence'] is None and payload['occurredAt'] is None
                    assert payload['location'] == dict(type='UNAVAILABLE', lat=None, lon=None, observedAt=None)
        print(name + ': PASS')
    subprocess.run(['C:/msys64/ucrt64/bin/gcov.exe', '--json-format', '-o', str(build), str(obj)], check=True, cwd=build)
    report = json.loads(gzip.decompress((build / 'host_test.gcov.json.gz').read_bytes()))
    lines = next(f['lines'] for f in report['files'] if f['file'].replace('\\', '/').endswith('/device_telemetry.c'))
    coverage = 100 * sum(line['count'] > 0 for line in lines) / len(lines)
    result = dict(scenarios_passed=len(SCENARIOS), line_coverage_percent=round(coverage, 2), hardware_verified=False)
    (build / 'results.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result)); assert coverage >= 80

if __name__ == '__main__':
    main()
