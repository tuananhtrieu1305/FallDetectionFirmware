#pragma once

/* Copy to main/network_config.local.h (Git ignored), then fill in locally.
 * Use a 2.4 GHz WPA2-Personal / compatible WPA3-Personal access point.
 * Empty SSID disables Wi-Fi without starting the worker/driver.
 * C strings: escape a quotation mark as \" and a backslash as \\.
 * Do not paste real credentials into this template or sdkconfig.
 */
#define NETWORK_WIFI_SSID ""
#define NETWORK_WIFI_PASSWORD ""

/* Fill in ONLY the ignored local header. Use broker LAN IP, not localhost.
 * mqtt:// is for a controlled demo LAN. mqtts:// requires a trusted CA PEM.
 * Do not run the mock and real board with the same device ID simultaneously.
 */
#define NETWORK_MQTT_BROKER_URI ""
#define NETWORK_MQTT_DEVICE_ID "waist-esp32s3-001"
#define NETWORK_MQTT_USERNAME ""
#define NETWORK_MQTT_PASSWORD ""
/* Optional for mqtts://: #define NETWORK_MQTT_SERVER_CERT_PEM "...CA PEM..." */

/* Controlled demo only: set 1 locally to accept TEST_ALERT + Enter on UART0.
 * Does not sound the buzzer, execute MQTT commands or initiate rescue.
 */
#define NETWORK_TEST_ALERT_SERIAL_ENABLED 0

/* Demo only, after agreeing the Phase 5 command profile. SNTP UTC is required. */
#define NETWORK_COMMANDS_ENABLED 0
#define NETWORK_TIME_SERVER "pool.ntp.org"
