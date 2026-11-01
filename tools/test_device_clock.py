"""Check actual clock module against fake SNTP callback/monotonic clock."""
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    build=ROOT/'build/phase8_2_5/clock_tests';inc=build/'include'
    for name in ['esp_err.h','esp_log.h','esp_timer.h','esp_netif_sntp.h','freertos/FreeRTOS.h']:
        p=inc/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('#include "host_sdk.h"\n')
    exe=build/'clock_tests.exe'
    subprocess.run(['C:/msys64/ucrt64/bin/gcc.exe','-std=gnu17','-Wall','-Wextra','-Werror','-I',str(inc),'-I',str(ROOT/'tests/device_clock'),'-I',str(ROOT/'main'),str(ROOT/'tests/device_clock/host_test.c'),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
if __name__=='__main__':main()
