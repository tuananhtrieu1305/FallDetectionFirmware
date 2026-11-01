"""Test real MQTT manager with bounded fake SDK I/O, no radio or broker."""
import gzip
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ["invalid", "happy", "wait-wifi", "reconnect", "fragment", "bad-fragments",
             "queue-full", "publish", "publish-fail", "tx-full", "error", "no-suback",
             "subscribe-fail", "suback-denied", "queue1-fail", "queue2-fail", "task-fail",
             "init-fail", "register-fail", "start-fail", "max-frame-zero-first", "tls-config"]

def main():
    build = ROOT / "build/phase8_2_3/host_tests"
    include = build / "include"
    for name in ("esp_err.h", "esp_netif.h", "esp_event.h", "esp_log.h", "esp_timer.h", "mqtt_client.h",
                 "wifi_manager.h", "freertos/FreeRTOS.h", "freertos/task.h", "freertos/queue.h"):
        p = include / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('#include "host_sdk.h"\n', encoding="utf-8")
    cc = "C:/msys64/ucrt64/bin/gcc.exe"
    flags = ["-std=gnu17", "-Wall", "-Wextra", "-Werror", "-g", "--coverage",
             "-I", str(include), "-I", str(ROOT / "tests/mqtt_manager"), "-I", str(ROOT / "main")]
    for stem, source in (("mqtt_manager", "main/mqtt_manager.c"), ("host_test", "tests/mqtt_manager/host_test.c")):
        subprocess.run([cc, *flags, "-c", str(ROOT / source), "-o", str(build / (stem + ".o"))], check=True)
        (build / (stem + ".gcda")).unlink(missing_ok=True)
    exe = build / "mqtt_tests.exe"
    subprocess.run([cc, "--coverage", str(build / "mqtt_manager.o"), str(build / "host_test.o"), "-o", str(exe)], check=True)
    for name in SCENARIOS:
        subprocess.run([str(exe), name], check=True, cwd=build)
    subprocess.run(["C:/msys64/ucrt64/bin/gcov.exe", "--json-format", "-o", str(build), str(ROOT / "main/mqtt_manager.c")], check=True, cwd=build)
    data = json.loads(gzip.decompress((build / "mqtt_manager.gcov.json.gz").read_bytes()))
    lines = next(f["lines"] for f in data["files"] if f["file"].replace("\\", "/").endswith("/mqtt_manager.c"))
    coverage = 100 * sum(l["count"] > 0 for l in lines) / len(lines)
    report = {"scenarios_passed": len(SCENARIOS), "line_coverage_percent": round(coverage, 2), "hardware_verified": False}
    (build / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    assert coverage >= 80

if __name__ == "__main__":
    main()
