"""Fault injection of checked APIs in actual alert_manager.c, no physical sound."""
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    build=ROOT/'build/phase8_2_5/buzzer_tests';inc=build/'include'
    for name in ['esp_err.h','esp_log.h','esp_timer.h','driver/gpio.h','driver/ledc.h','freertos/FreeRTOS.h','freertos/task.h']:
        p=inc/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('#include "host_sdk.h"\n')
    exe=build/'buzzer_tests.exe'
    subprocess.run(['C:/msys64/ucrt64/bin/gcc.exe','-std=gnu17','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections','-Wl,--gc-sections',
                    '-I',str(inc),'-I',str(ROOT/'tests/buzzer_checked'),'-I',str(ROOT/'main'),str(ROOT/'tests/buzzer_checked/host_test.c'),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
if __name__=='__main__':main()
