/* Deterministic integration tests of the real wifi_manager.c with fake SDK I/O.
 * Virtual time replaces the scheduler/radio; this is NOT hardware evidence.
 */
#include "host_sdk.h"
#include "wifi_manager.h"
#include <assert.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

const char host_wifi_event[] = "WIFI", host_ip_event[] = "IP";
static esp_event_handler_t wifi_handler, ip_handler;
static TaskFunction_t worker;
static void *worker_arg;
static esp_netif_t netif;
static jmp_buf finish;
static int64_t now_us, end_us = 180000000;
static uint32_t notifications;
static int init_step, fail_step, connect_mode, attempts, disconnects, recover_after;
static int handlers, netifs, drivers, task_fail;
static bool power_save_disabled;
static int worker_core = -1;
static bool shared_loop, callback_active, immediate_loss_checked, no_start_event;
static int64_t attempt_times[256];
static wifi_config_t installed_config;
typedef struct { int64_t at; int kind; } scheduled_event_t;
static scheduled_event_t events[256];
static size_t event_count;
enum { EV_ASSOCIATE, EV_IP, EV_DISCONNECT, EV_LOST_IP, EV_FOREIGN_IP,
       EV_ZERO_IP, EV_STOP };

static esp_err_t operation(void) { return ++init_step == fail_step ? ESP_FAIL : ESP_OK; }
static void schedule(int64_t at, int kind)
{
    assert(event_count < 256);
    size_t i = event_count++;
    while (i && events[i - 1].at > at) { events[i] = events[i - 1]; --i; }
    events[i] = (scheduled_event_t){at, kind};
}
static void dispatch(int kind)
{
    callback_active = true;
    wifi_event_sta_disconnected_t down = {.reason = 201};
    ip_event_got_ip_t ip = {.esp_netif = &netif, .ip_info.ip.addr = 0x0201a8c0};
    if (kind == EV_ASSOCIATE) wifi_handler(NULL, WIFI_EVENT, WIFI_EVENT_STA_CONNECTED, NULL);
    else if (kind == EV_DISCONNECT) wifi_handler(NULL, WIFI_EVENT, WIFI_EVENT_STA_DISCONNECTED, &down);
    else if (kind == EV_STOP) wifi_handler(NULL, WIFI_EVENT, WIFI_EVENT_STA_STOP, NULL);
    else if (kind == EV_LOST_IP) ip_handler(NULL, IP_EVENT, IP_EVENT_STA_LOST_IP, &netif);
    else {
        if (kind == EV_FOREIGN_IP) ip.esp_netif = (esp_netif_t *)(uintptr_t)99;
        if (kind == EV_ZERO_IP) ip.ip_info.ip.addr = 0;
        ip_handler(NULL, IP_EVENT, IP_EVENT_STA_GOT_IP, &ip);
    }
    callback_active = false;
    if (kind == EV_DISCONNECT || kind == EV_LOST_IP || kind == EV_STOP) {
        assert(!wifi_manager_is_connected());
        immediate_loss_checked = true;
    }
}

BaseType_t xTaskCreate(TaskFunction_t fn, const char *name, uint32_t stack,
    void *arg, unsigned priority, TaskHandle_t *handle)
{
    (void)name; (void)stack;
    assert(priority < 12); /* Preserve sensor priority. */
    if (task_fail) return 0;
    worker = fn; worker_arg = arg; *handle = (void *)(uintptr_t)1;
    return pdPASS;
}
BaseType_t xTaskCreatePinnedToCore(TaskFunction_t fn, const char *name, uint32_t stack,
    void *arg, unsigned priority, TaskHandle_t *handle, int core)
{
    worker_core = core;
    return xTaskCreate(fn, name, stack, arg, priority, handle);
}
BaseType_t xTaskNotifyGive(TaskHandle_t task) { assert(task); ++notifications; return pdPASS; }
uint32_t ulTaskNotifyTake(BaseType_t clear, TickType_t wait)
{
    (void)clear;
    if (notifications) { uint32_t n = notifications; notifications = 0; return n; }
    int64_t deadline = wait == portMAX_DELAY ? end_us : now_us + (int64_t)wait * 10000;
    if (event_count && events[0].at <= deadline && events[0].at < end_us) {
        now_us = events[0].at;
        int kind = events[0].kind;
        memmove(events, events + 1, --event_count * sizeof(events[0]));
        dispatch(kind);
        uint32_t n = notifications; notifications = 0; return n;
    }
    if (deadline >= end_us) { now_us = end_us; longjmp(finish, 1); }
    assert(deadline > now_us); /* Detect busy-spin on zero-tick waits. */
    now_us = deadline;
    return 0;
}
void vTaskDelete(TaskHandle_t task) { (void)task; longjmp(finish, 1); }
int64_t esp_timer_get_time(void) { return now_us; }
const char *esp_err_to_name(esp_err_t error) { (void)error; return "HOST_ERROR"; }
void host_log(const char *format, ...)
{
    char text[512]; va_list args;
    va_start(args, format); vsnprintf(text, sizeof(text), format, args); va_end(args);
    assert(strstr(text, "private-test-password") == NULL);
    assert(strstr(text, "private-test-ssid") == NULL);
}
esp_err_t nvs_flash_init(void) { return operation(); }
esp_err_t esp_netif_init(void) { return operation(); }
esp_err_t esp_event_loop_create_default(void)
{ esp_err_t e = operation(); return e != ESP_OK ? e : shared_loop ? ESP_ERR_INVALID_STATE : ESP_OK; }
esp_netif_t *esp_netif_new(const esp_netif_config_t *config)
{ assert(config); if (operation() != ESP_OK) return NULL; ++netifs; return &netif; }
esp_err_t esp_netif_attach_wifi_station(esp_netif_t *p)
{ assert(p == &netif); return operation(); }
esp_err_t esp_wifi_set_default_wifi_sta_handlers(void) { return operation(); }
void esp_netif_destroy_default_wifi(void *p) { assert(p == &netif); --netifs; }
esp_err_t esp_wifi_init(const wifi_init_config_t *config)
{ assert(config); esp_err_t e = operation(); if (e == ESP_OK) ++drivers; return e; }
esp_err_t esp_event_handler_instance_register(esp_event_base_t base, int32_t id,
    esp_event_handler_t fn, void *arg, esp_event_handler_instance_t *instance)
{
    (void)id; (void)arg;
    esp_err_t e = operation(); if (e != ESP_OK) return e;
    if (base == WIFI_EVENT) wifi_handler = fn; else ip_handler = fn;
    *instance = (void *)(uintptr_t)++handlers;
    return ESP_OK;
}
esp_err_t esp_event_handler_instance_unregister(esp_event_base_t base, int32_t id,
    esp_event_handler_instance_t instance)
{ (void)base; (void)id; assert(instance); --handlers; return ESP_OK; }
esp_err_t esp_wifi_set_storage(int storage) { assert(storage == WIFI_STORAGE_RAM); return operation(); }
esp_err_t esp_wifi_set_ps(int mode) { assert(mode == WIFI_PS_NONE); power_save_disabled = true; return operation(); }
esp_err_t esp_wifi_set_mode(int mode) { assert(mode == WIFI_MODE_STA); return operation(); }
esp_err_t esp_wifi_set_config(int interface, wifi_config_t *config)
{
    assert(interface == WIFI_IF_STA);
    assert(config->sta.threshold.authmode == WIFI_AUTH_WPA2_PSK);
    installed_config = *config; return operation();
}
esp_err_t esp_wifi_start(void)
{
    assert(!callback_active && power_save_disabled);
    esp_err_t e = operation();
    if (e == ESP_OK && !no_start_event) wifi_handler(NULL, WIFI_EVENT, WIFI_EVENT_STA_START, NULL);
    return e;
}
esp_err_t esp_wifi_connect(void)
{
    assert(!callback_active && attempts < 256);
    attempt_times[attempts++] = now_us;
    if (recover_after && attempts >= recover_after) connect_mode = 0;
    if (connect_mode == 1) return ESP_FAIL;
    if (connect_mode == 2) { schedule(now_us + 10000, EV_ASSOCIATE); return ESP_OK; }
    if (connect_mode == 3) { schedule(now_us + 10000, EV_DISCONNECT); return ESP_OK; }
    schedule(now_us + 10000, EV_ASSOCIATE);
    schedule(now_us + 20000, EV_IP);
    return ESP_OK;
}
esp_err_t esp_wifi_disconnect(void)
{ assert(!callback_active); ++disconnects; schedule(now_us + 10000, EV_DISCONNECT); return ESP_OK; }
esp_err_t esp_wifi_stop(void) { return ESP_OK; }
esp_err_t esp_wifi_deinit(void) { --drivers; return ESP_OK; }

static wifi_manager_snapshot_t snapshot(void)
{ wifi_manager_snapshot_t s; assert(wifi_manager_get_snapshot(&s) == ESP_OK); return s; }
static void run(void) { if (setjmp(finish) == 0) worker(worker_arg); }
static const wifi_manager_config_t config = {"private-test-ssid", "private-test-password"};

int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *name = argv[1];
    if (!strcmp(name, "invalid")) {
        assert(wifi_manager_test_disconnect() == ESP_ERR_INVALID_STATE);
        assert(wifi_manager_get_snapshot(NULL) == ESP_ERR_INVALID_ARG);
        assert(!wifi_manager_is_connected());
        assert(wifi_manager_start(NULL) == ESP_ERR_INVALID_ARG);
        wifi_manager_config_t c = {NULL, "12345678"};
        assert(wifi_manager_start(&c) == ESP_ERR_INVALID_ARG);
        c = (wifi_manager_config_t){"", ""};
        assert(wifi_manager_start(&c) == ESP_ERR_NOT_FOUND);
        assert(snapshot().state == WIFI_MANAGER_DISABLED && !worker);
        c = (wifi_manager_config_t){"ssid", NULL};
        assert(wifi_manager_start(&c) == ESP_ERR_INVALID_ARG);
        c = (wifi_manager_config_t){"ssid", "1234567"};
        assert(wifi_manager_start(&c) == ESP_ERR_INVALID_ARG);
        c = (wifi_manager_config_t){"123456789012345678901234567890123", "12345678"};
        assert(wifi_manager_start(&c) == ESP_ERR_INVALID_ARG);
        c = (wifi_manager_config_t){"ssid", "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"};
        assert(wifi_manager_start(&c) == ESP_ERR_INVALID_ARG);
        c.password = "12345678901234567890123456789012345678901234567890123456789012345";
        assert(wifi_manager_start(&c) == ESP_ERR_INVALID_ARG);
        return 0;
    }
    if (!strcmp(name, "task-fail")) {
        task_fail = 1;
        assert(wifi_manager_start(&config) == ESP_ERR_NO_MEM);
        assert(snapshot().state == WIFI_MANAGER_ERROR);
        assert(handlers == 0 && drivers == 0 && netifs == 0 && !worker);
        return 0;
    }
    if (!strcmp(name, "task-fail-retry")) {
        task_fail = 1;
        assert(wifi_manager_start(&config) == ESP_ERR_NO_MEM);
        assert(handlers == 0 && drivers == 0 && netifs == 0 && !worker);
        task_fail = 0;
        /* A retry must recreate the radio without stale handlers/netifs. */
    }
    if (!strncmp(name, "init-fail-", 10)) fail_step = atoi(name + 10);
    if (fail_step) {
        assert(wifi_manager_start(&config) != ESP_OK);
        assert(snapshot().state == WIFI_MANAGER_ERROR);
        assert(!wifi_manager_is_connected());
        assert(handlers == 0 && drivers == 0 && netifs == 0 && !worker);
        assert(wifi_manager_start(&config) == ESP_ERR_INVALID_STATE);
        printf("PASS %s synchronous error/cleanup\n", name);
        return 0;
    }
    if (!strcmp(name, "no-start-event")) no_start_event = true;
    if (!strcmp(name, "shared-loop")) shared_loop = true;
    if (!strcmp(name, "sync-fail")) connect_mode = 1;
    if (!strcmp(name, "no-dhcp")) { connect_mode = 2; end_us = 70000000; }
    if (!strcmp(name, "offline") || !strcmp(name, "duplicate-down")) connect_mode = 3;
    if (!strcmp(name, "reconnect")) { schedule(5000000, EV_DISCONNECT); end_us = 10000000; }
    if (!strcmp(name, "recover-backoff")) {
        connect_mode = 3; recover_after = 4;
        schedule(10000000, EV_DISCONNECT); end_us = 13000000;
    }
    if (!strcmp(name, "lost-ip")) { schedule(5000000, EV_LOST_IP); end_us = 10000000; }
    if (!strcmp(name, "duplicate-down")) {
        for (int i = 0; i < 50; ++i) schedule(100000 + i * 10000, EV_DISCONNECT);
    }
    if (!strcmp(name, "invalid-ip")) {
        connect_mode = 2; end_us = 2000000;
        schedule(100000, EV_FOREIGN_IP); schedule(200000, EV_ZERO_IP);
    }
    if (!strcmp(name, "stopped")) { schedule(5000000, EV_STOP); end_us = 10000000; }
    if (!strcmp(name, "max-config")) {
        wifi_manager_config_t max_config = {
            "12345678901234567890123456789012",
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"};
        assert(wifi_manager_start(&max_config) == ESP_OK);
    } else assert(wifi_manager_start(&config) == ESP_OK);
    if (!strcmp(name, "radio-ready-before-return")) {
        /* Sampling may start as soon as start() returns: RF/driver startup
         * must already be done, without depending on association or DHCP.
         */
        assert(drivers == 1 && netifs == 1 && handlers == 2 && worker_core == 0);
        assert(init_step == 14 && worker != NULL && power_save_disabled);
        assert(attempts == 0 && !wifi_manager_is_connected());
    }
    assert(wifi_manager_start(&config) == ESP_ERR_INVALID_STATE);
    run();
    wifi_manager_snapshot_t s = snapshot();
    if (!strcmp(name, "stopped") || no_start_event) {
        assert(s.state == WIFI_MANAGER_ERROR && s.last_error != ESP_OK);
        assert(!s.connected && handlers == 0 && drivers == 0 && netifs == 0);
    } else if (!strcmp(name, "sync-fail") || !strcmp(name, "offline") || !strcmp(name, "duplicate-down")) {
        assert(!s.connected && attempts >= 7 && attempts < 15);
        assert(s.retry_delay_ms == 30000);
        for (int i = 1; i < attempts; ++i) {
            int64_t expected = i < 6 ? (1000000LL << (i - 1)) : 30000000;
            assert(attempt_times[i] - attempt_times[i - 1] >= expected);
        }
    } else if (!strcmp(name, "no-dhcp")) {
        assert(!s.connected && disconnects >= 2 && attempts >= 2);
        assert(attempt_times[1] - attempt_times[0] >= 30000000);
    } else if (!strcmp(name, "invalid-ip")) assert(!s.connected);
    else {
        assert(s.connected && s.state == WIFI_MANAGER_CONNECTED);
        assert(s.ip_info.ip.addr == 0x0201a8c0 && s.retry_delay_ms == 0);
        if (!strcmp(name, "reconnect") || !strcmp(name, "lost-ip")) {
            assert(attempts == 2 && immediate_loss_checked);
            assert(attempt_times[1] >= 6000000);
        }
        if (!strcmp(name, "recover-backoff")) {
            assert(attempts == 5 && immediate_loss_checked);
            assert(attempt_times[4] >= 11000000 && attempt_times[4] < 12000000);
        }
        if (!strcmp(name, "max-config")) {
            assert(installed_config.sta.ssid[31] == '2');
            assert(installed_config.sta.password[63] == 'f');
        }
    }
    if (!strcmp(name, "local-drop")) {
        assert(wifi_manager_test_disconnect() == ESP_OK);
        end_us += 10000000;
        run();
        assert(snapshot().connected && attempts == 2 && immediate_loss_checked);
    }
    printf("PASS %s attempts=%d\n", name, attempts);
    return 0;
}
