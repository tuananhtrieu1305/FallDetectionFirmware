
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <math.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/i2c_master.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_rom_sys.h"

#include "bmi270.h"
#include "bmp3.h"
#include "alert_manager.h"
#include "sensor_manager.h"
#include "sensor_bus.h"
#include "gnss_manager.h"
#include "lte_manager.h"
#include "wifi_manager.h"
#include "mqtt_manager.h"
#include "device_telemetry.h"
#include "command_processor.h"
#include "device_clock.h"
#include "network_config.h"

/* PHASE 4 wiring and driver interface are intentionally preserved. */
#define I2C_SDA_GPIO 8
#define I2C_SCL_GPIO 9
#define I2C_PORT I2C_NUM_0
#define I2C_FREQ_HZ 100000
#define BMI270_I2C_ADDRESS 0x68
#define BMI270_RW_LEN 46
#define BMP3_I2C_ADDRESS 0x76

static const char *TAG = "SENSOR_TEST";
static const char *BMI_TAG = "BMI270";
static const char *BMP_TAG = "BMP388";

/* =========================================================
 * Interface contexts
 * ========================================================= */

typedef struct
{
    i2c_master_dev_handle_t dev_handle;
} bmi270_intf_context_t;

typedef struct
{
    i2c_master_dev_handle_t dev_handle;
} bmp3_intf_context_t;

/* =========================================================
 * BMI270 I2C callbacks
 * ========================================================= */

static BMI2_INTF_RETURN_TYPE bmi270_i2c_read(
    uint8_t reg_addr,
    uint8_t *reg_data,
    uint32_t len,
    void *intf_ptr)
{
    bmi270_intf_context_t *ctx =
        (bmi270_intf_context_t *)intf_ptr;

    if (ctx == NULL ||
        reg_data == NULL ||
        len == 0)
    {
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

    if (err != ESP_OK)
    {
        return -1;
    }

    return BMI2_INTF_RET_SUCCESS;
}

static BMI2_INTF_RETURN_TYPE bmi270_i2c_write(
    uint8_t reg_addr,
    const uint8_t *reg_data,
    uint32_t len,
    void *intf_ptr)
{
    bmi270_intf_context_t *ctx =
        (bmi270_intf_context_t *)intf_ptr;

    if (ctx == NULL ||
        reg_data == NULL ||
        len == 0 ||
        len > BMI2_MAX_BUFFER_SIZE)
    {
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

    if (err != ESP_OK)
    {
        return -1;
    }

    return BMI2_INTF_RET_SUCCESS;
}

static void bmi270_delay_us(
    uint32_t period,
    void *intf_ptr)
{
    (void)intf_ptr;

    esp_rom_delay_us(period);
}

/* =========================================================
 * BMP3 I2C callbacks
 * ========================================================= */

static BMP3_INTF_RET_TYPE bmp3_i2c_read(
    uint8_t reg_addr,
    uint8_t *reg_data,
    uint32_t len,
    void *intf_ptr)
{
    bmp3_intf_context_t *ctx =
        (bmp3_intf_context_t *)intf_ptr;

    if (ctx == NULL ||
        reg_data == NULL ||
        len == 0)
    {
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

    if (err != ESP_OK)
    {
        return -1;
    }

    return BMP3_INTF_RET_SUCCESS;
}

static BMP3_INTF_RET_TYPE bmp3_i2c_write(
    uint8_t reg_addr,
    const uint8_t *reg_data,
    uint32_t len,
    void *intf_ptr)
{
    bmp3_intf_context_t *ctx =
        (bmp3_intf_context_t *)intf_ptr;

    if (ctx == NULL ||
        reg_data == NULL ||
        len == 0)
    {
        return -1;
    }

    uint8_t tx_buffer[len + 1];

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

    if (err != ESP_OK)
    {
        return -1;
    }

    return BMP3_INTF_RET_SUCCESS;
}

static void bmp3_delay_us(
    uint32_t period,
    void *intf_ptr)
{
    (void)intf_ptr;

    esp_rom_delay_us(period);
}

/* =========================================================
 * BMI270 configuration
 * ========================================================= */

static int8_t configure_bmi270(
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

    if (rslt != BMI2_OK)
    {
        return rslt;
    }

    config[0].cfg.acc.odr =
        BMI2_ACC_ODR_100HZ;

    config[0].cfg.acc.range =
        BMI2_ACC_RANGE_8G;

    config[0].cfg.acc.bwp =
        BMI2_ACC_NORMAL_AVG4;

    config[0].cfg.acc.filter_perf =
        BMI2_PERF_OPT_MODE;

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

    rslt =
        bmi2_set_sensor_config(
            config,
            2,
            bmi
        );

    if (rslt != BMI2_OK)
    {
        return rslt;
    }

    uint8_t sensor_list[2] =
    {
        BMI2_ACCEL,
        BMI2_GYRO
    };

    return bmi2_sensor_enable(
        sensor_list,
        2,
        bmi
    );
}

/* =========================================================
 * BMP388 configuration
 * ========================================================= */

static int8_t configure_bmp3(
    struct bmp3_dev *bmp,
    struct bmp3_settings *settings)
{
    memset(
        settings,
        0,
        sizeof(*settings)
    );

    settings->press_en =
        BMP3_ENABLE;

    settings->temp_en =
        BMP3_ENABLE;

    settings->odr_filter.press_os =
        BMP3_OVERSAMPLING_4X;

    settings->odr_filter.temp_os =
        BMP3_OVERSAMPLING_2X;

    settings->odr_filter.odr =
        BMP3_ODR_25_HZ;

    settings->odr_filter.iir_filter =
        BMP3_IIR_FILTER_COEFF_3;

    uint16_t settings_sel =
        BMP3_SEL_PRESS_EN |
        BMP3_SEL_TEMP_EN |
        BMP3_SEL_PRESS_OS |
        BMP3_SEL_ODR |
        BMP3_SEL_IIR_FILTER;

    int8_t rslt =
        bmp3_set_sensor_settings(
            settings_sel,
            settings,
            bmp
        );

    if (rslt != BMP3_OK)
    {
        return rslt;
    }

    settings->op_mode =
        BMP3_MODE_NORMAL;

    return bmp3_set_op_mode(
        settings,
        bmp
    );
}

void app_main(void)
{
    /* =====================================================
     * Alert hardware
     * ===================================================== */

    esp_err_t err =
        alert_manager_init();

    if (err != ESP_OK)
    {
        ESP_LOGE(
            "ALERT",
            "alert_manager_init FAILED: %s",
            esp_err_to_name(err)
        );

        return;
    }

    ESP_LOGI(
        "ALERT",
        "alert_manager_init PASS"
    );

    /*
     * Force safe startup states.
     */
    vibration_off();
    buzzer_off();

    /* =====================================================
     * Startup
     * ===================================================== */

    ESP_LOGI(
        TAG,
        "========================================"
    );

    ESP_LOGI(
        TAG,
        "PHASE 6.2 - SENSOR MANAGER + GNSS RAW NMEA"
    );

    ESP_LOGI(
        TAG,
        "SDA = GPIO%d",
        I2C_SDA_GPIO
    );

    ESP_LOGI(
        TAG,
        "SCL = GPIO%d",
        I2C_SCL_GPIO
    );

    ESP_LOGI(
        TAG,
        "========================================"
    );

    /* =====================================================
     * Shared I2C bus
     * ===================================================== */

    i2c_master_bus_config_t bus_config =
    {
        .clk_source =
            I2C_CLK_SRC_DEFAULT,

        .i2c_port =
            I2C_PORT,

        .sda_io_num =
            I2C_SDA_GPIO,

        .scl_io_num =
            I2C_SCL_GPIO,

        .glitch_ignore_cnt =
            7,

        .flags.enable_internal_pullup =
            true,
    };

    i2c_master_bus_handle_t bus_handle =
        NULL;

    err =
        sensor_bus_create(
            &bus_config,
            &bus_handle
        );

    if (err != ESP_OK)
    {
        ESP_LOGE(
            TAG,
            "I2C bus init FAILED: %s",
            esp_err_to_name(err)
        );

        return;
    }

    ESP_LOGI(
        TAG,
        "I2C bus init PASS"
    );

    /* =====================================================
     * Probe sensors
     * ===================================================== */

    err =
        i2c_master_probe(
            bus_handle,
            BMI270_I2C_ADDRESS,
            100
        );

    if (err != ESP_OK)
    {
        ESP_LOGE(
            BMI_TAG,
            "NOT detected at 0x%02X",
            BMI270_I2C_ADDRESS
        );

        return;
    }

    ESP_LOGI(
        BMI_TAG,
        "Detected at 0x%02X",
        BMI270_I2C_ADDRESS
    );

    err =
        i2c_master_probe(
            bus_handle,
            BMP3_I2C_ADDRESS,
            100
        );

    if (err != ESP_OK)
    {
        ESP_LOGE(
            BMP_TAG,
            "NOT detected at 0x%02X",
            BMP3_I2C_ADDRESS
        );

        return;
    }

    ESP_LOGI(
        BMP_TAG,
        "Detected at 0x%02X",
        BMP3_I2C_ADDRESS
    );

    /* =====================================================
     * Add BMI270
     * ===================================================== */

    i2c_device_config_t bmi_config =
    {
        .dev_addr_length =
            I2C_ADDR_BIT_LEN_7,

        .device_address =
            BMI270_I2C_ADDRESS,

        .scl_speed_hz =
            I2C_FREQ_HZ,
    };

    i2c_master_dev_handle_t bmi_handle =
        NULL;

    err =
        i2c_master_bus_add_device(
            bus_handle,
            &bmi_config,
            &bmi_handle
        );

    if (err != ESP_OK)
    {
        ESP_LOGE(
            BMI_TAG,
            "Add device FAILED"
        );

        return;
    }

    /* =====================================================
     * Add BMP388
     * ===================================================== */

    i2c_device_config_t bmp_config =
    {
        .dev_addr_length =
            I2C_ADDR_BIT_LEN_7,

        .device_address =
            BMP3_I2C_ADDRESS,

        .scl_speed_hz =
            I2C_FREQ_HZ,
    };

    i2c_master_dev_handle_t bmp_handle =
        NULL;

    err =
        i2c_master_bus_add_device(
            bus_handle,
            &bmp_config,
            &bmp_handle
        );

    if (err != ESP_OK)
    {
        ESP_LOGE(
            BMP_TAG,
            "Add device FAILED"
        );

        return;
    }

    /* =====================================================
     * BMI270 init
     * ===================================================== */

    static bmi270_intf_context_t bmi_ctx;
    bmi_ctx.dev_handle = bmi_handle;

    static struct bmi2_dev bmi;

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
        &bmi_ctx;

    bmi.read_write_len =
        BMI270_RW_LEN;

    bmi.config_file_ptr =
        NULL;

    int8_t bmi_rslt =
        bmi270_init(
            &bmi
        );

    if (bmi_rslt != BMI2_OK)
    {
        ESP_LOGE(
            BMI_TAG,
            "Init FAILED: %d",
            bmi_rslt
        );

        return;
    }

    ESP_LOGI(
        BMI_TAG,
        "Init PASS, CHIP_ID = 0x%02X",
        bmi.chip_id
    );

    bmi_rslt =
        configure_bmi270(
            &bmi
        );

    if (bmi_rslt != BMI2_OK)
    {
        ESP_LOGE(
            BMI_TAG,
            "Configuration FAILED: %d",
            bmi_rslt
        );

        return;
    }

    ESP_LOGI(
        BMI_TAG,
        "ACC 100Hz +/-8g + GYRO 100Hz +/-2000dps PASS"
    );

    /* =====================================================
     * BMP388 init
     * ===================================================== */

    static bmp3_intf_context_t bmp_ctx;
    bmp_ctx.dev_handle = bmp_handle;

    static struct bmp3_dev bmp;

    memset(
        &bmp,
        0,
        sizeof(bmp)
    );

    bmp.intf =
        BMP3_I2C_INTF;

    bmp.read =
        bmp3_i2c_read;

    bmp.write =
        bmp3_i2c_write;

    bmp.delay_us =
        bmp3_delay_us;

    bmp.intf_ptr =
        &bmp_ctx;

    int8_t bmp_rslt =
        bmp3_init(
            &bmp
        );

    if (bmp_rslt != BMP3_OK)
    {
        ESP_LOGE(
            BMP_TAG,
            "bmp3_init FAILED: %d",
            bmp_rslt
        );

        return;
    }

    ESP_LOGI(
        BMP_TAG,
        "BMP3 init PASS, CHIP_ID = 0x%02X",
        bmp.chip_id
    );

    struct bmp3_settings bmp_settings;

    bmp_rslt =
        configure_bmp3(
            &bmp,
            &bmp_settings
        );

    if (bmp_rslt != BMP3_OK)
    {
        ESP_LOGE(
            BMP_TAG,
            "Configuration FAILED: %d",
            bmp_rslt
        );

        return;
    }

    ESP_LOGI(
        BMP_TAG,
        "Pressure + temperature enabled"
    );

    vTaskDelay(
        pdMS_TO_TICKS(100)
    );

    /* =====================================================
     * PHASE 5 - Sensor Manager
     * ===================================================== */

    /*
     * Only Sensor Task reads BMI270.
     * BMP388 is initialized, preserving Phase 5 behavior.
     */
    ESP_LOGI(
        TAG,
        "BMI270 manager init; BMP388 initialized but NOT sampled yet"
    );

    ESP_LOGI(
        TAG,
        "Vibration and buzzer OFF for clean acquisition"
    );

    /* Complete boot-only NVS/PHY/radio preparation BEFORE starting the 10 ms
     * acquisition timer. Association/DHCP/reconnect remain in the Wi-Fi worker;
     * no AP is required to reach sensor_manager_start().
     */
#if LTE_DIAG_SKIP_WIFI
    ESP_LOGW("LTE", "Wi-Fi intentionally skipped for selected LTE diagnostic this boot; "
             "normal startup remains available when diagnostic isolation is disabled");
#else
    const wifi_manager_config_t wifi_config = {
        .ssid = NETWORK_WIFI_SSID,
        .password = NETWORK_WIFI_PASSWORD,
    };
    err = wifi_manager_start(&wifi_config);
    bool wifi_prepared = err == ESP_OK;
    if (err == ESP_ERR_NOT_FOUND)
    {
        ESP_LOGW("WIFI_MANAGER", "Wi-Fi disabled: configure main/network_config.local.h locally");
    }
    else if (err != ESP_OK)
    {
        ESP_LOGE("WIFI_MANAGER", "start failed: %s; sensor startup continues", esp_err_to_name(err));
    }
    const mqtt_manager_config_t mqtt_config = {
        .broker_uri = NETWORK_MQTT_BROKER_URI,
        .device_id = NETWORK_MQTT_DEVICE_ID,
        .username = NETWORK_MQTT_USERNAME,
        .password = NETWORK_MQTT_PASSWORD,
        .server_certificate = NETWORK_MQTT_SERVER_CERT_PEM,
    };
    err = mqtt_manager_start(&mqtt_config);
    if (err == ESP_ERR_NOT_FOUND)
    {
        ESP_LOGW("MQTT_MANAGER", "disabled: set broker URI in ignored network_config.local.h");
    }
    else if (err != ESP_OK)
    {
        ESP_LOGE("MQTT_MANAGER", "start failed: %s; sensor startup continues", esp_err_to_name(err));
    }
    command_processor_init(NETWORK_COMMANDS_ENABLED != 0);
    if (NETWORK_COMMANDS_ENABLED && wifi_prepared) {
        err = device_clock_init(NETWORK_TIME_SERVER);
        if (err != ESP_OK) ESP_LOGE("DEVICE_CLOCK", "init failed: %s; commands require UTC", esp_err_to_name(err));
    }
#endif

    err = sensor_manager_start(&bmi, &bmp);

    if (err != ESP_OK)
    {
        ESP_LOGE(
            TAG,
            "sensor_manager_start FAILED: %s",
            esp_err_to_name(err)
        );

        return;
    }

    ESP_LOGI(
        TAG,
        "Sensor Manager started; requested interval = 10000 us"
    );

    /* =====================================================
     * PHASE 6.2 - NEO-M8N GNSS
     * ===================================================== */

    /*
     * Start a separate UART1 task.
     * A GNSS error must not stop Sensor Manager.
     */

    err = gnss_manager_start();

    if (err != ESP_OK)
    {
        ESP_LOGE(
            TAG,
            "gnss_manager_start FAILED: %s",
            esp_err_to_name(err)
        );
    }
    else
    {
        ESP_LOGI(
            TAG,
            "GNSS raw NMEA task started on UART1 / GPIO15 / 9600 baud"
        );
    }

    /* =====================================================
     * Selected LTE diagnostic (exclusive owner of GPIO17/18)
     * ===================================================== */

    err = lte_manager_start();

    if (err != ESP_OK)
    {
        ESP_LOGE(
            TAG,
            "lte_manager_start FAILED: %s",
            esp_err_to_name(err)
        );
    }
    else
    {
        ESP_LOGI(
            TAG,
            "LTE diagnostic task scheduled; see LTE mode/init/result logs"
        );
    }

    /* Independent, one-shot GPIO6 PWM diagnostic. GPIO5 automatic diagnostic
     * is disabled so the two actuators cannot run together.
     */
#if LTE_UART_AT_DIAG
    ESP_LOGI("LTE", "Phase 11.11: automatic buzzer test skipped; motor test already disabled");
#else
    err = buzzer_gpio6_diag_start();
    if (err != ESP_OK)
    {
        ESP_LOGE(
            "BUZZER_GPIO6_DIAG",
            "start failed: %s; OFF cleanup attempted, other tasks continue",
            esp_err_to_name(err)
        );
    }
#endif

    /* Publisher never runs in Sensor Task or MQTT callback. GNSS and the
     * actuator driver are initialized before read-only snapshots are used.
     */
#if !LTE_DIAG_SKIP_WIFI
    err = device_telemetry_start(NETWORK_MQTT_DEVICE_ID,
                                 NETWORK_TEST_ALERT_SERIAL_ENABLED != 0);
    if (err != ESP_OK) {
        ESP_LOGE("DEVICE_TELEMETRY", "start failed: %s; sensor continues", esp_err_to_name(err));
    }
#endif

    /* =====================================================
     * Main task idle loop
     * ===================================================== */

    /*
     * Keep app_main alive.
     * Bosch contexts above have static storage.
     */

    while (1)
    {
        /*
         * GPIO4 diagnostic only. Discard the debounced event so a test press
         * cannot trigger alert, actuator, MQTT, or emergency behavior.
         * The main task is low priority; 20 ms polling supports the existing
         * 40 ms debounce without changing Sensor Manager timing.
         */
        (void)button_pressed();

        vTaskDelay(
            pdMS_TO_TICKS(20)
        );
    }
}
