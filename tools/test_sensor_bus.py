"""Verify actual boot helper routes I2C IRQ allocation to acquisition core."""
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    d=ROOT/'build/phase8_2_6/sensor_bus_tests';inc=d/'include'
    for name in ['esp_err.h','esp_log.h','driver/i2c_master.h','freertos/FreeRTOS.h','freertos/task.h']:
        p=inc/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('#include "host_sdk.h"\n')
    exe=d/'bus_tests.exe'
    subprocess.run(['C:/msys64/ucrt64/bin/gcc.exe','-std=gnu17','-Wall','-Wextra','-Werror','-I',str(inc),'-I',str(ROOT/'tests/sensor_bus'),'-I',str(ROOT/'main'),str(ROOT/'main/sensor_bus.c'),str(ROOT/'tests/sensor_bus/host_test.c'),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
if __name__=='__main__':main()
