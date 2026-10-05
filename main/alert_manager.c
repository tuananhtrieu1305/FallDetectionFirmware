#include "alert_manager.h"

#include <stdint.h>

#include "driver/gpio.h"
#include "driver/ledc.h"

#include "esp_log.h"
#include "esp_timer.h"


/* =========================================================
 * Hardware mapping
 * ========================================================= */

/*
 * BUTTON
 *
 * Test thực tế:
 *
 * idle    = LOW
 * pressed = HIGH
 */
#define BUTTON_GPIO                 GPIO_NUM_4
#define BUTTON_ACTIVE_LEVEL         1

/*
 * Debounce time:
 * 40 ms
 */
#define BUTTON_DEBOUNCE_US          40000


/*
 * VIBRATION MOTOR - V919
 *
 * Test thực tế:
 *
 * VCC  = 3.3V
 * LOW  = OFF
 * HIGH = ON
 */
#define VIBRATION_GPIO              GPIO_NUM_5
#define VIBRATION_OFF_LEVEL         0
#define VIBRATION_ON_LEVEL          1


/*
 * BUZZER - MH-FMD
 *
 * Test thực tế:
 *
 * DC LOW chỉ tạo click nhỏ.
 * PWM ~2.5 kHz tạo tiếng rõ.
 *
 * GPIO6 is driven by LEDC.
 */
#define BUZZER_GPIO                 GPIO_NUM_6

#define BUZZER_PWM_FREQ_HZ          2500

#define BUZZER_LEDC_MODE            LEDC_LOW_SPEED_MODE
#define BUZZER_LEDC_TIMER           LEDC_TIMER_0
#define BUZZER_LEDC_CHANNEL         LEDC_CHANNEL_0

#define BUZZER_LEDC_RESOLUTION      LEDC_TIMER_10_BIT

/*
 * 10-bit:
 *
 * full scale ~= 1024
 *
 * 512 ~= 50% duty cycle.
 */
#define BUZZER_PWM_DUTY             512


static const char *TAG = "ALERT_MANAGER";


/* =========================================================
 * Button debounce state
 * ========================================================= */

static int button_last_raw_level = 0;
static int button_stable_level = 0;

static int64_t button_raw_since_us = 0;


/* =========================================================
 * Vibration
 * ========================================================= */

void vibration_on(void)
{
    gpio_set_level(
        VIBRATION_GPIO,
        VIBRATION_ON_LEVEL
    );
}


void vibration_off(void)
{
    gpio_set_level(
        VIBRATION_GPIO,
        VIBRATION_OFF_LEVEL
    );
}


/* =========================================================
 * Buzzer
 * ========================================================= */

void buzzer_on(void)
{
    /*
     * Because LEDC output is configured as inverted:
     *
     * duty = 50%
     *
     * produces:
     *
     * HIGH / LOW / HIGH / LOW ...
     *
     * at approximately 2.5 kHz.
     */

    esp_err_t err =
        ledc_set_duty(
            BUZZER_LEDC_MODE,
            BUZZER_LEDC_CHANNEL,
            BUZZER_PWM_DUTY
        );


    if (err != ESP_OK) {

        ESP_LOGE(
            TAG,
            "buzzer_on ledc_set_duty failed: %s",
            esp_err_to_name(err)
        );

        return;
    }


    err =
        ledc_update_duty(
            BUZZER_LEDC_MODE,
            BUZZER_LEDC_CHANNEL
        );


    if (err != ESP_OK) {

        ESP_LOGE(
            TAG,
            "buzzer_on ledc_update_duty failed: %s",
            esp_err_to_name(err)
        );
    }
}


void buzzer_off(void)
{
    /*
     * LEDC output is inverted.
     *
     * duty = 0
     *
     * therefore physical GPIO output becomes HIGH.
     *
     * The buzzer module is low-level triggered,
     * so HIGH is the safe/silent level.
     */

    esp_err_t err =
        ledc_set_duty(
            BUZZER_LEDC_MODE,
            BUZZER_LEDC_CHANNEL,
            0
        );


    if (err != ESP_OK) {

        ESP_LOGE(
            TAG,
            "buzzer_off ledc_set_duty failed: %s",
            esp_err_to_name(err)
        );

        return;
    }


    err =
        ledc_update_duty(
            BUZZER_LEDC_MODE,
            BUZZER_LEDC_CHANNEL
        );


    if (err != ESP_OK) {

        ESP_LOGE(
            TAG,
            "buzzer_off ledc_update_duty failed: %s",
            esp_err_to_name(err)
        );
    }
}


/* =========================================================
 * Button
 * ========================================================= */

bool button_pressed(void)
{
    int raw_level =
        gpio_get_level(
            BUTTON_GPIO
        );


    int64_t now_us =
        esp_timer_get_time();


    /*
     * Raw signal has changed.
     *
     * Start a new debounce interval.
     */
    if (raw_level != button_last_raw_level) {

        button_last_raw_level =
            raw_level;

        button_raw_since_us =
            now_us;

        return false;
    }


    /*
     * Raw level has remained unchanged long enough.
     */
    if ((raw_level != button_stable_level) &&
        ((now_us - button_raw_since_us) >=
         BUTTON_DEBOUNCE_US)) {

        button_stable_level =
            raw_level;


        /*
         * Only emit an event when entering
         * the PRESSED state.
         *
         * Release only updates the stable state.
         */
        if (button_stable_level ==
            BUTTON_ACTIVE_LEVEL) {

            return true;
        }
    }


    return false;
}


/* =========================================================
 * Initialize button
 * ========================================================= */

static esp_err_t button_init(void)
{
    /*
     * We already experimentally confirmed
     * the module is ACTIVE-HIGH.
     *
     * Internal pull-down is enabled as an
     * additional safe idle bias.
     *
     * This is also useful when the button
     * is temporarily disconnected.
     */

    gpio_config_t cfg = {
        .pin_bit_mask =
            (1ULL << BUTTON_GPIO),

        .mode =
            GPIO_MODE_INPUT,

        .pull_up_en =
            GPIO_PULLUP_DISABLE,

        .pull_down_en =
            GPIO_PULLDOWN_ENABLE,

        .intr_type =
            GPIO_INTR_DISABLE,
    };


    esp_err_t err =
        gpio_config(&cfg);


    if (err != ESP_OK) {
        return err;
    }


    int initial_level =
        gpio_get_level(
            BUTTON_GPIO
        );


    button_last_raw_level =
        initial_level;

    button_stable_level =
        initial_level;

    button_raw_since_us =
        esp_timer_get_time();


    ESP_LOGI(
        TAG,
        "Button initialized: GPIO4, ACTIVE-HIGH"
    );


    return ESP_OK;
}


/* =========================================================
 * Initialize vibration motor
 * ========================================================= */

static esp_err_t vibration_init(void)
{
    /*
     * Preload safe state.
     */
    gpio_set_level(
        VIBRATION_GPIO,
        VIBRATION_OFF_LEVEL
    );


    gpio_config_t cfg = {
        .pin_bit_mask =
            (1ULL << VIBRATION_GPIO),

        .mode =
            GPIO_MODE_OUTPUT,

        .pull_up_en =
            GPIO_PULLUP_DISABLE,

        .pull_down_en =
            GPIO_PULLDOWN_ENABLE,

        .intr_type =
            GPIO_INTR_DISABLE,
    };


    esp_err_t err =
        gpio_config(&cfg);


    if (err != ESP_OK) {
        return err;
    }


    vibration_off();


    ESP_LOGI(
        TAG,
        "Vibration initialized: GPIO5, ACTIVE-HIGH"
    );


    return ESP_OK;
}


/* =========================================================
 * Initialize buzzer PWM
 * ========================================================= */

static esp_err_t buzzer_init(void)
{
    /*
     * Before handing GPIO6 to LEDC,
     * force it HIGH.
     *
     * HIGH = silent for this buzzer module.
     */
    gpio_config_t gpio_cfg = {
        .pin_bit_mask =
            (1ULL << BUZZER_GPIO),

        .mode =
            GPIO_MODE_OUTPUT,

        .pull_up_en =
            GPIO_PULLUP_ENABLE,

        .pull_down_en =
            GPIO_PULLDOWN_DISABLE,

        .intr_type =
            GPIO_INTR_DISABLE,
    };


    esp_err_t err =
        gpio_config(&gpio_cfg);


    if (err != ESP_OK) {
        return err;
    }


    gpio_set_level(
        BUZZER_GPIO,
        1
    );


    /*
     * LEDC timer:
     * 2.5 kHz.
     */
    ledc_timer_config_t timer_cfg = {
        .speed_mode =
            BUZZER_LEDC_MODE,

        .duty_resolution =
            BUZZER_LEDC_RESOLUTION,

        .timer_num =
            BUZZER_LEDC_TIMER,

        .freq_hz =
            BUZZER_PWM_FREQ_HZ,

        .clk_cfg =
            LEDC_AUTO_CLK,

        .deconfigure =
            false,
    };


    err =
        ledc_timer_config(
            &timer_cfg
        );


    if (err != ESP_OK) {
        return err;
    }


    /*
     * Important:
     *
     * output_invert = 1
     *
     * means duty=0 results in a physical HIGH output.
     *
     * That lets buzzer_off() use duty=0 while still
     * keeping this active-low module silent.
     */
    ledc_channel_config_t channel_cfg = {
        .gpio_num =
            BUZZER_GPIO,

        .speed_mode =
            BUZZER_LEDC_MODE,

        .channel =
            BUZZER_LEDC_CHANNEL,

        .intr_type =
            LEDC_INTR_DISABLE,

        .timer_sel =
            BUZZER_LEDC_TIMER,

        .duty =
            0,

        .hpoint =
            0,

        .flags = {
            .output_invert = 1,
        },
    };


    err =
        ledc_channel_config(
            &channel_cfg
        );


    if (err != ESP_OK) {
        return err;
    }


    buzzer_off();


    ESP_LOGI(
        TAG,
        "Buzzer initialized: GPIO6, PWM=%d Hz",
        BUZZER_PWM_FREQ_HZ
    );


    return ESP_OK;
}


/* =========================================================
 * Public initialization
 * ========================================================= */

esp_err_t alert_manager_init(void)
{
    ESP_LOGI(
        TAG,
        "========================================"
    );

    ESP_LOGI(
        TAG,
        "Initializing alert manager"
    );


    esp_err_t err;


    /*
     * Outputs first:
     *
     * bring them to safe state as soon as
     * app_main starts.
     */
    err =
        vibration_init();


    if (err != ESP_OK) {

        ESP_LOGE(
            TAG,
            "Vibration init failed: %s",
            esp_err_to_name(err)
        );

        return err;
    }


    err =
        buzzer_init();


    if (err != ESP_OK) {

        ESP_LOGE(
            TAG,
            "Buzzer init failed: %s",
            esp_err_to_name(err)
        );

        return err;
    }


    err =
        button_init();


    if (err != ESP_OK) {

        ESP_LOGE(
            TAG,
            "Button init failed: %s",
            esp_err_to_name(err)
        );

        return err;
    }


    ESP_LOGI(
        TAG,
        "Alert manager initialized"
    );

    ESP_LOGI(
        TAG,
        "========================================"
    );


    return ESP_OK;
}