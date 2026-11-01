#pragma once

#include <stdbool.h>

#include "esp_err.h"

/*
 * Initialize:
 *
 * Button:
 *   GPIO4
 *   currently configured ACTIVE-HIGH; verify physical levels from diagnostic
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
 * Start the independent GPIO5 hardware diagnostic once per boot.
 * The one-shot worker waits for startup to settle, drives the motor for
 * 500 ms, forces it OFF on every exit path, then deletes itself.
 */
esp_err_t motor_gpio5_diag_start(void);

/*
 * Start the independent GPIO6 PWM diagnostic once per boot.
 * The one-shot worker waits for startup to settle, sounds for 500 ms,
 * forces the LEDC channel OFF on every exit path, then deletes itself.
 */
esp_err_t buzzer_gpio6_diag_start(void);


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

/* Read LEDC duty only; does not control the actuator or certify audible sound. */
esp_err_t alert_manager_get_buzzer_state(bool *on);

/* Checked LEDC operations for demo worker only. Success requires duty readback;
 * no claim about a fall state or acoustic confirmation. Existing void APIs stay.
 */
esp_err_t buzzer_start_checked(void);
esp_err_t buzzer_stop_checked(void);


/*
 * Debounced button event.
 *
 * Returns true exactly once for each valid press.
 *
 * This function should be called periodically
 * from the main loop.
 */
bool button_pressed(void);
