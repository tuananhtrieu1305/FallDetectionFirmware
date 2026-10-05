#include <stdint.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "driver/i2c_master.h"

#include "esp_err.h"
#include "esp_log.h"
#include "esp_rom_sys.h"

#include "bmi270.h"

#include "alert_manager.h"


/* =========================================================
 * BMI270 hardware configuration
 * ========================================================= */

#define BMI270_SDA_GPIO        8
#define BMI270_SCL_GPIO        9

#define BMI270_I2C_PORT        I2C_NUM_0

#define BMI270_I2C_ADDRESS     0x68

#define BMI270_I2C_FREQ_HZ     100000

#define BMI270_RW_LEN          46


/* Physical ranges */
#define ACC_RANGE_G            8.0f
#define GYR_RANGE_DPS          2000.0f

#define GRAVITY_MPS2           9.80665f


static const char *TAG =
    "BMI270";

static const char *ALERT_TEST_TAG =
    "ALERT_TEST";


/* =========================================================
 * BMI270 interface context
 * ========================================================= */

typedef struct
{
    i2c_master_dev_handle_t dev_handle;
} bmi270_intf_context_t;


/* =========================================================
 * Bosch SensorAPI -> ESP-IDF I2C read
 * ========================================================= */

static BMI2_INTF_RETURN_TYPE bmi270_i2c_read(
    uint8_t reg_addr,
    uint8_t *reg_data,
    uint32_t len,
    void *intf_ptr)
{
    bmi270_intf_context_t *ctx =
        (bmi270_intf_context_t *)intf_ptr;


    if ((ctx == NULL) ||
        (reg_data == NULL) ||
        (len == 0)) {

        return -1;
    }


    esp_err_t err =
        i2c_master_transmit_receive(
            ctx->dev_handle,
            &reg_addr,
            1,
            reg_data,
            len,
            1000
        );


    if (err != ESP_OK) {
        return -1;
    }


    return BMI2_INTF_RET_SUCCESS;
}


/* =========================================================
 * Bosch SensorAPI -> ESP-IDF I2C write
 * ========================================================= */

static BMI2_INTF_RETURN_TYPE bmi270_i2c_write(
    uint8_t reg_addr,
    const uint8_t *reg_data,
    uint32_t len,
    void *intf_ptr)
{
    bmi270_intf_context_t *ctx =
        (bmi270_intf_context_t *)intf_ptr;


    if ((ctx == NULL) ||
        (reg_data == NULL) ||
        (len == 0) ||
        (len > BMI2_MAX_BUFFER_SIZE)) {

        return -1;
    }


    uint8_t tx_buffer[
        BMI2_MAX_BUFFER_SIZE + 1
    ];


    tx_buffer[0] =
        reg_addr;


    memcpy(
        &tx_buffer[1],
        reg_data,
        len
    );


    esp_err_t err =
        i2c_master_transmit(
            ctx->dev_handle,
            tx_buffer,
            len + 1,
            1000
        );


    if (err != ESP_OK) {
        return -1;
    }


    return BMI2_INTF_RET_SUCCESS;
}


/* =========================================================
 * Bosch delay callback
 * ========================================================= */

static void bmi270_delay_us(
    uint32_t period,
    void *intf_ptr)
{
    (void)intf_ptr;

    esp_rom_delay_us(
        period
    );
}


/* =========================================================
 * Conversion helpers
 * ========================================================= */

static float accel_raw_to_g(
    int16_t raw)
{
    return (
        (float)raw *
        ACC_RANGE_G
    ) / 32768.0f;
}


static float accel_raw_to_mps2(
    int16_t raw)
{
    return
        accel_raw_to_g(raw) *
        GRAVITY_MPS2;
}


static float gyro_raw_to_dps(
    int16_t raw)
{
    return (
        (float)raw *
        GYR_RANGE_DPS
    ) / 32768.0f;
}


/* =========================================================
 * Configure accelerometer + gyroscope
 * ========================================================= */

static int8_t configure_accel_gyro(
    struct bmi2_dev *bmi)
{
    struct bmi2_sens_config config[2];


    memset(
        config,
        0,
        sizeof(config)
    );


    config[0].type =
        BMI2_ACCEL;

    config[1].type =
        BMI2_GYRO;


    int8_t rslt =
        bmi2_get_sensor_config(
            config,
            2,
            bmi
        );


    if (rslt != BMI2_OK) {
        return rslt;
    }


    /* ---------------- ACCELEROMETER ---------------- */

    config[0].cfg.acc.odr =
        BMI2_ACC_ODR_100HZ;

    config[0].cfg.acc.range =
        BMI2_ACC_RANGE_8G;

    config[0].cfg.acc.bwp =
        BMI2_ACC_NORMAL_AVG4;

    config[0].cfg.acc.filter_perf =
        BMI2_PERF_OPT_MODE;


    /* ---------------- GYROSCOPE ---------------- */

    config[1].cfg.gyr.odr =
        BMI2_GYR_ODR_100HZ;

    config[1].cfg.gyr.range =
        BMI2_GYR_RANGE_2000;

    config[1].cfg.gyr.bwp =
        BMI2_GYR_NORMAL_MODE;

    config[1].cfg.gyr.noise_perf =
        BMI2_POWER_OPT_MODE;

    config[1].cfg.gyr.filter_perf =
        BMI2_PERF_OPT_MODE;


    return
        bmi2_set_sensor_config(
            config,
            2,
            bmi
        );
}


/* =========================================================
 * app_main
 * ========================================================= */

void app_main(void)
{
    /*
     * =====================================================
     * ALERT MANAGER
     *
     * Initialize this FIRST.
     *
     * This forces vibration/buzzer toward
     * their software-safe states as early
     * as possible.
     * =====================================================
     */

    esp_err_t err =
        alert_manager_init();


    if (err != ESP_OK) {

        ESP_LOGE(
            ALERT_TEST_TAG,
            "alert_manager_init FAILED: %s",
            esp_err_to_name(err)
        );

        return;
    }


    ESP_LOGI(
        TAG,
        "========================================"
    );

    ESP_LOGI(
        TAG,
        "BMI270 + ALERT MANAGER"
    );

    ESP_LOGI(
        TAG,
        "SDA          : GPIO%d",
        BMI270_SDA_GPIO
    );

    ESP_LOGI(
        TAG,
        "SCL          : GPIO%d",
        BMI270_SCL_GPIO
    );

    ESP_LOGI(
        TAG,
        "Address      : 0x%02X",
        BMI270_I2C_ADDRESS
    );

    ESP_LOGI(
        TAG,
        "Accel ODR    : 100 Hz"
    );

    ESP_LOGI(
        TAG,
        "Accel range  : +/- 8 g"
    );

    ESP_LOGI(
        TAG,
        "Gyro ODR     : 100 Hz"
    );

    ESP_LOGI(
        TAG,
        "Gyro range   : +/- 2000 dps"
    );

    ESP_LOGI(
        TAG,
        "========================================"
    );


    /* =====================================================
     * Create I2C master bus
     * ===================================================== */

    i2c_master_bus_config_t bus_config = {
        .clk_source =
            I2C_CLK_SRC_DEFAULT,

        .i2c_port =
            BMI270_I2C_PORT,

        .sda_io_num =
            BMI270_SDA_GPIO,

        .scl_io_num =
            BMI270_SCL_GPIO,

        .glitch_ignore_cnt =
            7,

        .flags.enable_internal_pullup =
            true,
    };


    i2c_master_bus_handle_t bus_handle =
        NULL;


    err =
        i2c_new_master_bus(
            &bus_config,
            &bus_handle
        );


    if (err != ESP_OK) {

        ESP_LOGE(
            TAG,
            "I2C bus init failed: %s",
            esp_err_to_name(err)
        );

        return;
    }


    /* =====================================================
     * Add BMI270
     * ===================================================== */

    i2c_device_config_t device_config = {
        .dev_addr_length =
            I2C_ADDR_BIT_LEN_7,

        .device_address =
            BMI270_I2C_ADDRESS,

        .scl_speed_hz =
            BMI270_I2C_FREQ_HZ,
    };


    i2c_master_dev_handle_t bmi270_handle =
        NULL;


    err =
        i2c_master_bus_add_device(
            bus_handle,
            &device_config,
            &bmi270_handle
        );


    if (err != ESP_OK) {

        ESP_LOGE(
            TAG,
            "Failed to add BMI270: %s",
            esp_err_to_name(err)
        );

        return;
    }


    /* =====================================================
     * Prepare Bosch SensorAPI
     * ===================================================== */

    bmi270_intf_context_t intf_context = {
        .dev_handle =
            bmi270_handle
    };


    struct bmi2_dev bmi;


    memset(
        &bmi,
        0,
        sizeof(bmi)
    );


    bmi.intf =
        BMI2_I2C_INTF;

    bmi.read =
        bmi270_i2c_read;

    bmi.write =
        bmi270_i2c_write;

    bmi.delay_us =
        bmi270_delay_us;

    bmi.intf_ptr =
        &intf_context;

    bmi.read_write_len =
        BMI270_RW_LEN;

    bmi.config_file_ptr =
        NULL;


    /* =====================================================
     * Initialize BMI270
     * ===================================================== */

    int8_t rslt =
        bmi270_init(
            &bmi
        );


    if (rslt != BMI2_OK) {

        ESP_LOGE(
            TAG,
            "bmi270_init FAILED: %d",
            rslt
        );

        return;
    }


    ESP_LOGI(
        TAG,
        "BMI270 init PASS, CHIP ID = 0x%02X",
        bmi.chip_id
    );


    /* =====================================================
     * Configure accel + gyro
     * ===================================================== */

    rslt =
        configure_accel_gyro(
            &bmi
        );


    if (rslt != BMI2_OK) {

        ESP_LOGE(
            TAG,
            "ACC/GYRO configuration FAILED: %d",
            rslt
        );

        return;
    }


    ESP_LOGI(
        TAG,
        "ACC/GYRO configuration PASS"
    );


    /* =====================================================
     * Enable sensors
     * ===================================================== */

    uint8_t sensor_list[2] = {
        BMI2_ACCEL,
        BMI2_GYRO
    };


    rslt =
        bmi2_sensor_enable(
            sensor_list,
            2,
            &bmi
        );


    if (rslt != BMI2_OK) {

        ESP_LOGE(
            TAG,
            "ACC/GYRO enable FAILED: %d",
            rslt
        );

        return;
    }


    ESP_LOGI(
        TAG,
        "ACC + GYRO enabled"
    );


    vTaskDelay(
        pdMS_TO_TICKS(100)
    );


    /* =====================================================
     * PHASE 4 API smoke test
     *
     * Current physical setup:
     * buzzer is connected.
     *
     * Vibration/button may currently be disconnected.
     *
     * No fall state machine yet.
     * ===================================================== */

    ESP_LOGI(
        ALERT_TEST_TAG,
        "========================================"
    );

    ESP_LOGI(
        ALERT_TEST_TAG,
        "ALERT MANAGER API TEST"
    );

    ESP_LOGI(
        ALERT_TEST_TAG,
        "Waiting 2 seconds before buzzer test"
    );


    buzzer_off();


    vTaskDelay(
        pdMS_TO_TICKS(2000)
    );


    ESP_LOGI(
        ALERT_TEST_TAG,
        "buzzer_on() - 2 seconds"
    );


    buzzer_on();


    vTaskDelay(
        pdMS_TO_TICKS(2000)
    );


    buzzer_off();


    ESP_LOGI(
        ALERT_TEST_TAG,
        "buzzer_off()"
    );


    ESP_LOGI(
        ALERT_TEST_TAG,
        "API test complete"
    );

    ESP_LOGI(
        ALERT_TEST_TAG,
        "========================================"
    );


    /* =====================================================
     * BMI270 normal read loop
     * ===================================================== */

    struct bmi2_sens_data sensor_data;


    memset(
        &sensor_data,
        0,
        sizeof(sensor_data)
    );


    uint32_t sample_count =
        0;


    TickType_t last_wake_time =
        xTaskGetTickCount();


    const TickType_t sample_period =
        pdMS_TO_TICKS(10);


    ESP_LOGI(
        TAG,
        "========================================"
    );

    ESP_LOGI(
        TAG,
        "BMI270 DATA STREAM STARTED"
    );

    ESP_LOGI(
        TAG,
        "Sensor ODR = 100 Hz"
    );

    ESP_LOGI(
        TAG,
        "Host polling ~= 100 Hz"
    );

    ESP_LOGI(
        TAG,
        "Serial display ~= 10 Hz"
    );

    ESP_LOGI(
        ALERT_TEST_TAG,
        "button_pressed() polling active"
    );

    ESP_LOGI(
        TAG,
        "========================================"
    );


    while (1) {

        /*
         * ---------------------------------------------
         * BMI270
         * ---------------------------------------------
         */

        rslt =
            bmi2_get_sensor_data(
                &sensor_data,
                &bmi
            );


        if (rslt != BMI2_OK) {

            ESP_LOGE(
                TAG,
                "Sensor read error: %d",
                rslt
            );

        }
        else if (
            (sensor_data.status &
             BMI2_DRDY_ACC) &&

            (sensor_data.status &
             BMI2_DRDY_GYR)
        ) {

            sample_count++;


            /*
             * Print approximately 10 Hz.
             */
            if ((sample_count % 10) == 0) {

                float ax_g =
                    accel_raw_to_g(
                        sensor_data.acc.x
                    );

                float ay_g =
                    accel_raw_to_g(
                        sensor_data.acc.y
                    );

                float az_g =
                    accel_raw_to_g(
                        sensor_data.acc.z
                    );


                float ax_ms2 =
                    accel_raw_to_mps2(
                        sensor_data.acc.x
                    );

                float ay_ms2 =
                    accel_raw_to_mps2(
                        sensor_data.acc.y
                    );

                float az_ms2 =
                    accel_raw_to_mps2(
                        sensor_data.acc.z
                    );


                float gx_dps =
                    gyro_raw_to_dps(
                        sensor_data.gyr.x
                    );

                float gy_dps =
                    gyro_raw_to_dps(
                        sensor_data.gyr.y
                    );

                float gz_dps =
                    gyro_raw_to_dps(
                        sensor_data.gyr.z
                    );


                ESP_LOGI(
                    TAG,

                    "RAW A[%6d %6d %6d] "
                    "G[%6d %6d %6d] | "
                    "ACC[g]=[%+.3f %+.3f %+.3f] | "
                    "ACC[m/s2]=[%+.2f %+.2f %+.2f] | "
                    "GYR[dps]=[%+.2f %+.2f %+.2f]",

                    sensor_data.acc.x,
                    sensor_data.acc.y,
                    sensor_data.acc.z,

                    sensor_data.gyr.x,
                    sensor_data.gyr.y,
                    sensor_data.gyr.z,

                    ax_g,
                    ay_g,
                    az_g,

                    ax_ms2,
                    ay_ms2,
                    az_ms2,

                    gx_dps,
                    gy_dps,
                    gz_dps
                );
            }
        }


        /*
         * ---------------------------------------------
         * BUTTON
         *
         * No state machine yet.
         *
         * Just verify API event.
         * ---------------------------------------------
         */

        if (button_pressed()) {

            ESP_LOGI(
                ALERT_TEST_TAG,
                "BUTTON_PRESSED"
            );
        }


        /*
         * ---------------------------------------------
         * Keep approximately 100 Hz host loop.
         * ---------------------------------------------
         */

        vTaskDelayUntil(
            &last_wake_time,
            sample_period
        );
    }
}