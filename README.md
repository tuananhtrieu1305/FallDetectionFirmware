# Fall Detection Firmware

Firmware for the wearable IoT fall-detection project.

## Hardware baseline

- MCU: ESP32-S3 N16R8
- Flash: 16 MB
- PSRAM: 8 MB
- Development board: 44-pin ESP32-S3 board
- USB-to-UART: CH343
- Wearable target position: waist / abdomen

## Development environment

- OS: Windows 11
- Framework: ESP-IDF v5.5.5
- Target: esp32s3
- IDE: Visual Studio Code + Espressif ESP-IDF extension
- ESP-IDF installation: managed by Espressif Installation Manager

Before running ESP-IDF commands in VS Code, use:

    Ctrl + Shift + P
    ESP-IDF: Open ESP-IDF Terminal

## Phase 0 verified

The following bring-up checks have passed on the physical board:

- ESP32-S3 detected successfully
- Silicon revision v0.2
- 16 MB external flash detected
- 8 MB PSRAM detected by esptool
- Build succeeds with ESP-IDF v5.5.5
- Firmware flashes successfully through the CH343 COM interface
- Serial monitor works at 115200 baud
- Software reboot works
- Physical reset works repeatedly
- Baseline firmware runs continuously and outputs a heartbeat

PSRAM is physically present but intentionally not enabled for application use during Phase 0.

## Build

Run:

    idf.py build

## Flash

Replace PORT with the COM port assigned by Windows:

    idf.py -p PORT flash

Example on the current development machine:

    idf.py -p COM5 flash

## Monitor

Run:

    idf.py -p PORT monitor

Exit the monitor with:

    Ctrl + ]

## Current firmware behavior

After boot, the firmware prints board and firmware information and then outputs:

    Heartbeat: firmware running

approximately every 5 seconds.

No sensors, GNSS, LTE modem, buzzer, vibration motor, button, or Edge AI are initialized in Phase 0.
