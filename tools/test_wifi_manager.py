"""Compile/run actual Wi-Fi manager against host SDK fakes; no radio/COM access."""
import argparse
import gzip
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ["radio-ready-before-return", "invalid", "local-drop", "task-fail", "task-fail-retry", "happy", "shared-loop", "max-config",
             "reconnect", "recover-backoff", "lost-ip", "sync-fail", "offline", "duplicate-down",
             "no-dhcp", "invalid-ip", "stopped", "no-start-event"] + [f"init-fail-{i}" for i in range(1, 15)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default="gcc")
    parser.add_argument("--gcov", default="gcov")
    args = parser.parse_args()
    cc, gcov = shutil.which(args.cc), shutil.which(args.gcov)
    if not cc or not gcov:
        raise SystemExit("Host GCC/gcov required (for example C:/msys64/ucrt64/bin).")
    build = ROOT / "build/phase8_2_2/host_tests"
    include = build / "include"
    include.mkdir(parents=True, exist_ok=True)
    headers = ["esp_err.h", "esp_netif.h", "esp_wifi.h", "esp_wifi_default.h",
               "esp_event.h", "esp_timer.h", "esp_log.h", "nvs_flash.h",
               "freertos/FreeRTOS.h", "freertos/task.h"]
    for name in headers:
        p = include / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('#include "host_sdk.h"\n', encoding="utf-8")
    flags = ["-std=gnu17", "-Wall", "-Wextra", "-Werror", "-g", "--coverage",
             "-I", str(include), "-I", str(ROOT / "tests/wifi_manager"),
             "-I", str(ROOT / "main")]
    for stem, source in [("wifi_manager", "main/wifi_manager.c"),
                         ("host_test", "tests/wifi_manager/host_test.c")]:
        subprocess.run([cc, *flags, "-c", str(ROOT / source), "-o", str(build / f"{stem}.o")],
                       check=True, cwd=build)
        (build / f"{stem}.gcda").unlink(missing_ok=True)
    executable = build / "wifi_manager_tests.exe"
    subprocess.run([cc, "--coverage", str(build / "wifi_manager.o"),
                    str(build / "host_test.o"), "-o", str(executable)], check=True)
    for scenario in SCENARIOS:
        subprocess.run([str(executable), scenario], check=True, cwd=build)
    subprocess.run([gcov, "--json-format", "--branch-counts", "--branch-probabilities",
                    "-o", str(build), str(ROOT / "main/wifi_manager.c")], check=True, cwd=build)
    coverage = json.loads(gzip.decompress((build / "wifi_manager.gcov.json.gz").read_bytes()))
    source = next(f for f in coverage["files"] if f["file"].replace("\\", "/").endswith("/wifi_manager.c"))
    executed = sum(line["count"] > 0 for line in source["lines"])
    total = len(source["lines"])
    percent = 100 * executed / total
    report = {"scenarios_passed": len(SCENARIOS), "lines_executed": executed,
              "lines_total": total, "line_coverage_percent": round(percent, 2),
              "hardware_verified": False}
    (build / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if percent < 80:
        raise SystemExit("Wi-Fi manager line coverage below 80%")


if __name__ == "__main__":
    main()
