#include "host_sdk.h"
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include "../../main/device_clock.c"
static int64_t mono;
static bool fail_init,fail_start;
static unsigned starts;
static esp_sntp_config_t installed;
static gnss_snapshot_t gnss;
esp_err_t gnss_manager_get_snapshot(gnss_snapshot_t *out){*out=gnss;return ESP_OK;}
int64_t esp_timer_get_time(void){return mono;}
esp_err_t esp_netif_sntp_init(const esp_sntp_config_t *c){installed=*c;return fail_init?ESP_FAIL:ESP_OK;}
esp_err_t esp_netif_sntp_start(void){++starts;return fail_start?ESP_FAIL:ESP_OK;}
void host_log(const char *fmt,...){(void)fmt;}
int main(void){
 assert(device_clock_now_ms()==-1);device_clock_poll(true);assert(!starts);
 assert(device_clock_init(NULL)==ESP_ERR_INVALID_ARG);assert(device_clock_init("")==ESP_ERR_INVALID_ARG);
 assert(device_clock_init("ntp://example")==ESP_ERR_INVALID_ARG);
 char huge[255];memset(huge,'x',254);huge[254]=0;assert(device_clock_init(huge)==ESP_ERR_INVALID_ARG);
 fail_init=true;assert(device_clock_init("time.example")==ESP_FAIL);fail_init=false;
 assert(device_clock_init("time.example")==ESP_OK);assert(!installed.start&&!installed.wait_for_sync);
 assert(device_clock_init("time.example")==ESP_ERR_INVALID_STATE);
 device_clock_poll(false);assert(!starts);fail_start=true;device_clock_poll(true);device_clock_poll(true);assert(starts==1);
 struct timeval tv={.tv_sec=1,.tv_usec=0};installed.sync_cb(&tv);assert(device_clock_now_ms()==-1);
 tv.tv_sec=1793444400;tv.tv_usec=123000;mono=2000000;installed.sync_cb(&tv);assert(device_clock_now_ms()==1793444400123LL);
 mono+=1500000;assert(device_clock_now_ms()==1793444401623LL);
 mono=1000000;assert(device_clock_now_ms()==-1);mono=2000000+3600000001LL;assert(device_clock_now_ms()==-1);
 gnss.source=GNSS_LOCATION_CURRENT;gnss.has_current=gnss.fix_valid=true;
 gnss.current_location.received_at_monotonic_us=mono;gnss.current_location.observed_at_utc_ms=1793444400123LL;
 assert(device_clock_now_ms()==1793444400123LL);mono+=5000001;assert(device_clock_now_ms()==-1);
 puts("clock source/init/expiry/invalid-response PASS; fake SDK, not real NTP");return 0;
}
