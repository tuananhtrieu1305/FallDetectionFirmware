#include "alert_manager.h"

#include <inttypes.h>
#include <stdint.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

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
 * Current firmware configuration only; physical module polarity is being
 * measured by BUTTON_GPIO4_DIAGNOSTIC before this assumption is changed.
 */
#define BUTTON_GPIO                 GPIO_NUM_4
#define BUTTON_ACTIVE_LEVEL         1

/*
 * Debounce time:
 * 40 ms
 */
#define BUTTON_DEBOUNCE_US          40000

// Temporary diagnostic. Set to 0 and rebuild to suppress GPIO4 level logs.
#define BUTTON_GPIO4_DIAGNOSTIC     1


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

#define MOTOR_GPIO5_DIAG            0
#define MOTOR_DIAG_START_DELAY_MS   5000
#define MOTOR_DIAG_ON_TIME_MS       500
#define MOTOR_DIAG_TASK_STACK       3072
#define MOTOR_DIAG_TASK_PRIORITY    2


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

#define BUZZER_GPIO6_DIAG           1
#define BUZZER_DIAG_START_DELAY_MS  5000
#define BUZZER_DIAG_ON_TIME_MS      500
#define BUZZER_DIAG_TASK_STACK      3072
#define BUZZER_DIAG_TASK_PRIORITY   2


static const char *TAG = "ALERT_MANAGER";


/* =========================================================
 * Button debounce state
 * ========================================================= */

static int button_last_raw_level = 0;
static int button_stable_level = 0;

static int64_t button_raw_since_us = 0;

static uint32_t button_raw_edges_since_stable = 0;
static uint32_t button_stable_transitions = 0;

static bool motor_diag_started = false;
static bool buzzer_diag_started = false;
static bool buzzer_initialized = false;

esp_err_t alert_manager_get_buzzer_state(bool *on)
{
    if (on == NULL) return ESP_ERR_INVALID_ARG;
    if (!buzzer_initialized) return ESP_ERR_INVALID_STATE;
    uint32_t duty = ledc_get_duty(BUZZER_LEDC_MODE, BUZZER_LEDC_CHANNEL);
    if (duty == LEDC_ERR_DUTY) return ESP_FAIL;
    *on = duty != 0;
    return ESP_OK;
}


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
 * Independent one-shot motor diagnostic
 * ========================================================= */

static void motor_gpio5_diag_task(void *arg)
{
    (void)arg;

    vTaskDelay(pdMS_TO_TICKS(MOTOR_DIAG_START_DELAY_MS));

    ESP_LOGI(
        TAG,
        "MOTOR TEST START | GPIO5 active-high | at_us=%" PRId64,
        esp_timer_get_time()
    );

    esp_err_t test_err =
        gpio_set_level(VIBRATION_GPIO, VIBRATION_OFF_LEVEL);

    if (test_err == ESP_OK) {
        test_err =
            gpio_set_level(VIBRATION_GPIO, VIBRATION_ON_LEVEL);
    }

    if (test_err == ESP_OK) {
        ESP_LOGI(
            TAG,
            "MOTOR ON | GPIO5=1 | at_us=%" PRId64
            " | duration_ms=%d | diagnostic_only=1 no_alert=1",
            esp_timer_get_time(),
            MOTOR_DIAG_ON_TIME_MS
        );

        vTaskDelay(pdMS_TO_TICKS(MOTOR_DIAG_ON_TIME_MS));
    } else {
        ESP_LOGE(
            TAG,
            "MOTOR ON FAILED | GPIO5 | error=%s",
            esp_err_to_name(test_err)
        );
    }

    // Cleanup is unconditional, including every handled failure above.
    esp_err_t off_err =
        gpio_set_level(VIBRATION_GPIO, VIBRATION_OFF_LEVEL);

    if (off_err == ESP_OK) {
        ESP_LOGI(
            TAG,
            "MOTOR OFF | GPIO5=0 | at_us=%" PRId64,
            esp_timer_get_time()
        );
    } else {
        ESP_LOGE(
            TAG,
            "MOTOR OFF FAILED | GPIO5 | error=%s",
            esp_err_to_name(off_err)
        );
    }

    ESP_LOG_LEVEL(
        (test_err == ESP_OK && off_err == ESP_OK)
            ? ESP_LOG_INFO
            : ESP_LOG_ERROR,
        TAG,
        "MOTOR TEST COMPLETE | result=%s | motor_off=%s"
        " | at_us=%" PRId64 " | runs_this_boot=1",
        (test_err == ESP_OK && off_err == ESP_OK) ? "PASS" : "FAIL",
        off_err == ESP_OK ? "CONFIRMED_BY_GPIO_DRIVER" : "FAILED",
        esp_timer_get_time()
    );

    vTaskDelete(NULL);
}


esp_err_t motor_gpio5_diag_start(void)
{
    if (!MOTOR_GPIO5_DIAG) {
        return ESP_OK;
    }

    if (motor_diag_started) {
        return ESP_ERR_INVALID_STATE;
    }

    motor_diag_started = true;

    // Keep the motor safe while the one-shot task waits for startup to settle.
    esp_err_t err =
        gpio_set_level(VIBRATION_GPIO, VIBRATION_OFF_LEVEL);

    if (err != ESP_OK) {
        // Best-effort second OFF attempt before reporting the start failure.
        esp_err_t cleanup_err =
            gpio_set_level(VIBRATION_GPIO, VIBRATION_OFF_LEVEL);

        if (cleanup_err != ESP_OK) {
            ESP_LOGE(
                TAG,
                "MOTOR OFF FAILED | GPIO5 | start_cleanup_error=%s",
                esp_err_to_name(cleanup_err)
            );
        }

        return err;
    }

    if (xTaskCreate(
            motor_gpio5_diag_task,
            "motor_gpio5_diag",
            MOTOR_DIAG_TASK_STACK,
            NULL,
            MOTOR_DIAG_TASK_PRIORITY,
            NULL) != pdPASS) {

        // No worker exists to perform cleanup, so force OFF here.
        esp_err_t cleanup_err =
            gpio_set_level(VIBRATION_GPIO, VIBRATION_OFF_LEVEL);

        if (cleanup_err == ESP_OK) {
            ESP_LOGI(
                TAG,
                "MOTOR OFF | GPIO5=0 | reason=task_create_failed"
            );
            return ESP_ERR_NO_MEM;
        }

        ESP_LOGE(
            TAG,
            "MOTOR OFF FAILED | GPIO5 | task_create_cleanup_error=%s",
            esp_err_to_name(cleanup_err)
        );
        return cleanup_err;
    }

    ESP_LOGI(
        TAG,
        "MOTOR_GPIO5_DIAG scheduled once | start_delay_ms=%d"
        " | on_time_ms=%d | task_priority=%d",
        MOTOR_DIAG_START_DELAY_MS,
        MOTOR_DIAG_ON_TIME_MS,
        MOTOR_DIAG_TASK_PRIORITY
    );

    return ESP_OK;
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
 * Independent one-shot buzzer diagnostic
 * ========================================================= */

static esp_err_t buzzer_apply_duty_checked(uint32_t duty)
{
    esp_err_t err =
        ledc_set_duty(
            BUZZER_LEDC_MODE,
            BUZZER_LEDC_CHANNEL,
            duty
        );

    if (err != ESP_OK) {
        return err;
    }

    return ledc_update_duty(
        BUZZER_LEDC_MODE,
        BUZZER_LEDC_CHANNEL
    );
}


static esp_err_t buzzer_force_off_checked(bool *used_fallback)
{
    if (used_fallback) {
        *used_fallback = false;
    }

    esp_err_t err = buzzer_apply_duty_checked(0);
    if (err == ESP_OK) {
        return ESP_OK;
    }

    if (used_fallback) {
        *used_fallback = true;
    }

    /* GPIO matrix output inversion remains enabled. LEDC idle level 0 therefore
     * produces the same physical HIGH/silent output as duty=0 in this setup.
     */
    return ledc_stop(
        BUZZER_LEDC_MODE,
        BUZZER_LEDC_CHANNEL,
        0
    );
}

esp_err_t buzzer_start_checked(void)
{
    if (!buzzer_initialized) return ESP_ERR_INVALID_STATE;
    esp_err_t err = buzzer_apply_duty_checked(BUZZER_PWM_DUTY);
    /* Wait one RTOS tick for the hardware PWM update, outside callbacks. */
    vTaskDelay(1);
    bool on = false;
    if (err == ESP_OK && alert_manager_get_buzzer_state(&on) == ESP_OK && on) return ESP_OK;
    bool fallback;
    buzzer_force_off_checked(&fallback);
    return err == ESP_OK ? ESP_FAIL : err;
}

esp_err_t buzzer_stop_checked(void)
{
    if (!buzzer_initialized) return ESP_ERR_INVALID_STATE;
    esp_err_t err = buzzer_apply_duty_checked(0);
    vTaskDelay(1);
    bool on = true;
    if (err == ESP_OK && alert_manager_get_buzzer_state(&on) == ESP_OK && !on) return ESP_OK;
    /* Best-effort safe fallback, but never claim ACK success after a failed
     * primary operation/readback even if the fallback has silenced the output.
     */
    bool fallback;
    buzzer_force_off_checked(&fallback);
    return err == ESP_OK ? ESP_FAIL : err;
}


static void buzzer_gpio6_diag_task(void *arg)
{
    (void)arg;

    vTaskDelay(pdMS_TO_TICKS(BUZZER_DIAG_START_DELAY_MS));

    ESP_LOGI(
        TAG,
        "BUZZER TEST START | GPIO6 LEDC PWM=%dHz | at_us=%" PRId64,
        BUZZER_PWM_FREQ_HZ,
        esp_timer_get_time()
    );

    bool start_off_fallback = false;
    esp_err_t test_err =
        buzzer_force_off_checked(&start_off_fallback);

    if (test_err == ESP_OK) {
        test_err = buzzer_apply_duty_checked(BUZZER_PWM_DUTY);
    }

    if (test_err == ESP_OK) {
        ESP_LOGI(
            TAG,
            "BUZZER ON | GPIO6 LEDC PWM=%dHz duty=%d"
            " | at_us=%" PRId64 " | duration_ms=%d"
            " | diagnostic_only=1 no_alert=1",
            BUZZER_PWM_FREQ_HZ,
            BUZZER_PWM_DUTY,
            esp_timer_get_time(),
            BUZZER_DIAG_ON_TIME_MS
        );

        vTaskDelay(pdMS_TO_TICKS(BUZZER_DIAG_ON_TIME_MS));
    } else {
        ESP_LOGE(
            TAG,
            "BUZZER ON FAILED | GPIO6 LEDC | error=%s",
            esp_err_to_name(test_err)
        );
    }

    // Cleanup is unconditional, including every handled failure above.
    bool off_fallback = false;
    esp_err_t off_err = buzzer_force_off_checked(&off_fallback);

    if (off_err != ESP_OK) {
        // Retry the complete OFF sequence once before reporting failure.
        off_err = buzzer_force_off_checked(&off_fallback);
    }

    if (off_err == ESP_OK) {
        ESP_LOGI(
            TAG,
            "BUZZER OFF | GPIO6 silent | at_us=%" PRId64
            " | fallback_used=%d",
            esp_timer_get_time(),
            (int)(start_off_fallback || off_fallback)
        );
    } else {
        ESP_LOGE(
            TAG,
            "BUZZER OFF FAILED | GPIO6 LEDC | error=%s",
            esp_err_to_name(off_err)
        );
    }

    ESP_LOG_LEVEL(
        (test_err == ESP_OK && off_err == ESP_OK)
            ? ESP_LOG_INFO
            : ESP_LOG_ERROR,
        TAG,
        "BUZZER TEST COMPLETE | result=%s | buzzer_off=%s"
        " | at_us=%" PRId64 " | runs_this_boot=1",
        (test_err == ESP_OK && off_err == ESP_OK) ? "PASS" : "FAIL",
        off_err == ESP_OK ? "CONFIRMED_BY_LEDC_DRIVER" : "FAILED",
        esp_timer_get_time()
    );

    vTaskDelete(NULL);
}


esp_err_t buzzer_gpio6_diag_start(void)
{
    if (!BUZZER_GPIO6_DIAG) {
        return ESP_OK;
    }

    if (buzzer_diag_started) {
        return ESP_ERR_INVALID_STATE;
    }

    buzzer_diag_started = true;

    bool used_fallback = false;
    esp_err_t err = buzzer_force_off_checked(&used_fallback);
    if (err != ESP_OK) {
        (void)buzzer_force_off_checked(NULL);
        return err;
    }

    if (xTaskCreate(
            buzzer_gpio6_diag_task,
            "buzzer_gpio6_diag",
            BUZZER_DIAG_TASK_STACK,
            NULL,
            BUZZER_DIAG_TASK_PRIORITY,
            NULL) != pdPASS) {

        esp_err_t cleanup_err = buzzer_force_off_checked(NULL);
        if (cleanup_err == ESP_OK) {
            ESP_LOGI(
                TAG,
                "BUZZER OFF | GPIO6 silent | reason=task_create_failed"
            );
            return ESP_ERR_NO_MEM;
        }

        ESP_LOGE(
            TAG,
            "BUZZER OFF FAILED | GPIO6 LEDC"
            " | task_create_cleanup_error=%s",
            esp_err_to_name(cleanup_err)
        );
        return cleanup_err;
    }

    ESP_LOGI(
        TAG,
        "BUZZER_GPIO6_DIAG scheduled once | start_delay_ms=%d"
        " | on_time_ms=%d | pwm_hz=%d | task_priority=%d"
        " | motor_diag=DISABLED",
        BUZZER_DIAG_START_DELAY_MS,
        BUZZER_DIAG_ON_TIME_MS,
        BUZZER_PWM_FREQ_HZ,
        BUZZER_DIAG_TASK_PRIORITY
    );

    return ESP_OK;
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

        ++button_raw_edges_since_stable;

        return false;
    }


    /*
     * Raw level has remained unchanged long enough.
     */
    if ((raw_level != button_stable_level) &&
        ((now_us - button_raw_since_us) >=
         BUTTON_DEBOUNCE_US)) {

        int previous_stable_level =
            button_stable_level;

        button_stable_level = raw_level;

        ++button_stable_transitions;

        if (BUTTON_GPIO4_DIAGNOSTIC) {
            ESP_LOGI(
                TAG,
                "BUTTON_GPIO4_DIAG transition=%" PRIu32
                " GPIO4=%d->%d candidate_at_us=%" PRId64
                " stable_at_us=%" PRId64
                " debounce_us=%d raw_edges=%" PRIu32
                " matches_configured_active=%d diagnostic_only=1 no_action=1",
                button_stable_transitions,
                previous_stable_level,
                button_stable_level,
                button_raw_since_us,
                now_us,
                BUTTON_DEBOUNCE_US,
                button_raw_edges_since_stable,
                button_stable_level == BUTTON_ACTIVE_LEVEL
            );
        }

        button_raw_edges_since_stable = 0;


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

    /* Discard bounce/noise that returned to the existing stable level. */
    if ((raw_level == button_stable_level) &&
        (button_raw_edges_since_stable > 0) &&
        ((now_us - button_raw_since_us) >= BUTTON_DEBOUNCE_US)) {

        button_raw_edges_since_stable = 0;
    }


    return false;
}


/* =========================================================
 * Initialize button
 * ========================================================= */

static esp_err_t button_init(void)
{
    /*
     * Keep the existing ACTIVE-HIGH configuration unchanged until the
     * diagnostic log establishes the module's real released/pressed levels.
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

    button_raw_edges_since_stable = 0;
    button_stable_transitions = 0;


    ESP_LOGI(
        TAG,
        "Button initialized: GPIO4, configured ACTIVE-HIGH; measurement pending"
    );

    if (BUTTON_GPIO4_DIAGNOSTIC) {
        ESP_LOGI(
            TAG,
            "BUTTON_GPIO4_DIAG initial GPIO4=%d at_us=%" PRId64
            " mode=INPUT pull_up=DISABLED pull_down=ENABLED"
            " configured_active_level=%d debounce_us=%d"
            " diagnostic_only=1 no_action=1",
            initial_level,
            button_raw_since_us,
            BUTTON_ACTIVE_LEVEL,
            BUTTON_DEBOUNCE_US
        );
    }


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
    esp_err_t err =
        gpio_set_level(
            VIBRATION_GPIO,
            VIBRATION_OFF_LEVEL
        );

    if (err != ESP_OK) {
        return err;
    }


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


    err = gpio_config(&cfg);


    if (err != ESP_OK) {
        return err;
    }


    err =
        gpio_set_level(
            VIBRATION_GPIO,
            VIBRATION_OFF_LEVEL
        );

    if (err != ESP_OK) {
        return err;
    }


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


    err =
        gpio_set_level(
            BUZZER_GPIO,
            1
        );

    if (err != ESP_OK) {
        return err;
    }


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


    bool used_fallback = false;
    err = buzzer_force_off_checked(&used_fallback);

    if (err != ESP_OK) {
        return err;
    }

    if (used_fallback) {
        ESP_LOGW(
            TAG,
            "Buzzer OFF required LEDC stop fallback during init"
        );
    }


    ESP_LOGI(
        TAG,
        "Buzzer initialized: GPIO6, PWM=%d Hz",
        BUZZER_PWM_FREQ_HZ
    );

    buzzer_initialized = true;


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
