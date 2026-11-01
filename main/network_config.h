#pragma once

/* Local credentials are intentionally absent from versioned configuration.
 * Copy network_config.example.h to network_config.local.h and edit locally.
 */
#if defined(NETWORK_LOCAL_CONFIG_PRESENT) && NETWORK_LOCAL_CONFIG_PRESENT
#include "network_config.local.h"
#endif

#ifndef NETWORK_WIFI_SSID
#define NETWORK_WIFI_SSID ""
#endif
#ifndef NETWORK_WIFI_PASSWORD
#define NETWORK_WIFI_PASSWORD ""
#endif

#ifndef NETWORK_MQTT_BROKER_URI
#define NETWORK_MQTT_BROKER_URI ""
#endif
#ifndef NETWORK_MQTT_DEVICE_ID
#define NETWORK_MQTT_DEVICE_ID "waist-esp32s3-001"
#endif
#ifndef NETWORK_MQTT_USERNAME
#define NETWORK_MQTT_USERNAME ""
#endif
#ifndef NETWORK_MQTT_PASSWORD
#define NETWORK_MQTT_PASSWORD ""
#endif
#ifndef NETWORK_MQTT_SERVER_CERT_PEM
#define NETWORK_MQTT_SERVER_CERT_PEM NULL
#endif

/* Opt-in local UART0 TEST_ALERT command. Never auto-publish at boot/reconnect. */
#ifndef NETWORK_TEST_ALERT_SERIAL_ENABLED
#define NETWORK_TEST_ALERT_SERIAL_ENABLED 0
#endif

/* User-approved demo profile; Backend must adopt its ACK/TTL addendum. */
#ifndef NETWORK_COMMANDS_ENABLED
#define NETWORK_COMMANDS_ENABLED 0
#endif
#ifndef NETWORK_TIME_SERVER
#define NETWORK_TIME_SERVER "pool.ntp.org"
#endif
