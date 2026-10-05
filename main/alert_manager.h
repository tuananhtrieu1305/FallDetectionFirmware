#pragma once

#include <stdbool.h>

#include "esp_err.h"

/*
 * Initialize:
 *
 * Button:
 *   GPIO4
 *   ACTIVE-HIGH
 *
 * Vibration motor:
 *   GPIO5
 *   ACTIVE-HIGH
 *
 * Buzzer:
 *   GPIO6
 *   PWM ~2.5 kHz
 */
esp_err_t alert_manager_init(void);


/*
 * Vibration motor control
 */
void vibration_on(void);
void vibration_off(void);


/*
 * Buzzer control
 *
 * buzzer_on():
 *   start continuous ~2.5 kHz tone
 *
 * buzzer_off():
 *   stop tone and force buzzer idle
 */
void buzzer_on(void);
void buzzer_off(void);


/*
 * Debounced button event.
 *
 * Returns true exactly once for each valid press.
 *
 * This function should be called periodically
 * from the main loop.
 */
bool button_pressed(void);