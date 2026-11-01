/* Actual command parser/state/execution ordering, with fake LEDC boundary. */
#include "host_sdk.h"
#include "command_processor.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
static bool on;
static bool fail_stop,fail_read,fail_on;
static unsigned stop_calls;
static const char *event="123e4567-e89b-42d3-a456-426614174000";
static int64_t utc=1793444400000LL;
esp_err_t alert_manager_get_buzzer_state(bool *p){if(fail_read)return ESP_FAIL;*p=on;return ESP_OK;}
esp_err_t buzzer_start_checked(void){if(fail_on)return ESP_FAIL;on=true;return ESP_OK;}
esp_err_t buzzer_stop_checked(void){++stop_calls;if(fail_stop)return ESP_FAIL;on=false;return ESP_OK;}
void host_log(const char *fmt,...){(void)fmt;}
static void init(void){command_processor_init(true);on=false;fail_read=fail_stop=fail_on=false;stop_calls=0;}
static void arm(void){assert(command_processor_arm_test(event,11000000)==ESP_OK);assert(on);}
static mqtt_manager_command_t frame(const char *id,const char *evt,const char *cmd,const char *issued){
 mqtt_manager_command_t f={.connection_epoch=1};
 f.length=(size_t)snprintf(f.payload,sizeof(f.payload),"{\"commandId\":\"%s\",\"eventId\":\"%s\",\"command\":\"%s\",\"issuedAt\":\"%s\"}",id,evt,cmd,issued);return f;
}
static void process(mqtt_manager_command_t f,int64_t now){command_processor_process(&f,1,now);}
static void expect(const char *result,const char *reason){char out[512];assert(command_processor_ack_json(out,sizeof(out))>0);assert(strstr(out,result)&&strstr(out,reason));printf("ACK %s\n",out);}
int main(void){
 char out[512];init();assert(!command_processor_ack_json(out,sizeof(out)));
 assert(command_processor_arm_test(event,0)!=ESP_OK);arm();
 mqtt_manager_command_t valid=frame("cmd-1",event,"STOP_BUZZER","2026-10-31T11:00:00Z");
 process(valid,utc);assert(!on&&stop_calls==1);expect("EXECUTED","STOPPED");assert(command_processor_ack_pending());
 command_processor_ack_queued();assert(!command_processor_ack_pending());
 process(valid,utc+60000);expect("EXECUTED","STOPPED");assert(stop_calls==1); /* cached duplicate, no execution */
 process(frame("cmd-1",event,"STOP_BUZZER","2026-10-31T11:00:01Z"),utc);expect("REJECTED","COMMAND_ID_REUSED");
 init();arm();process(valid,-1);expect("REJECTED","CLOCK_UNAVAILABLE");assert(on&&!stop_calls);
 init();arm();process(valid,utc+30001);expect("REJECTED","EXPIRED");assert(on);
 init();arm();process(valid,utc-5001);expect("REJECTED","FUTURE_ISSUED_AT");
 init();arm();process(valid,utc+30000);expect("EXECUTED","STOPPED");
 init();process(valid,utc);expect("REJECTED","EVENT_NOT_ACTIVE");
 init();arm();mqtt_manager_command_t stale=valid;stale.connection_epoch=0;process(stale,utc);expect("REJECTED","STALE_CONNECTION");assert(on);
 init();arm();process(frame("c2","223e4567-e89b-42d3-a456-426614174000","STOP_BUZZER","2026-10-31T11:00:00Z"),utc);expect("REJECTED","EVENT_NOT_ACTIVE");
 init();arm();on=false;process(valid,utc);expect("REJECTED","NOT_BUZZING");
 init();arm();fail_stop=true;process(valid,utc);expect("FAILED","STOP_FAILED");assert(on);process(valid,utc);assert(stop_calls==1);
 init();arm();fail_read=true;process(valid,utc);expect("FAILED","ACTUATOR_UNAVAILABLE");
 init();arm();process(frame("c2",event,"UNKNOWN","2026-10-31T11:00:00Z"),utc);expect("REJECTED","UNSUPPORTED_COMMAND");
 const char *bad[]={"[]","{}","null","{\"commandId\":1}","{\"commandId\":\"x\",\"commandId\":\"y\"}",
  "{\"commandId\":\"x\\u0000z\"}","{\"x\":{}}", "{\"x\":[1]}","{} trailing"};
 for(unsigned i=0;i<sizeof(bad)/sizeof(*bad);++i){init();arm();mqtt_manager_command_t f={.connection_epoch=1};strcpy(f.payload,bad[i]);f.length=strlen(bad[i]);process(f,utc);assert(!command_processor_ack_pending()&&on);}
 const char *dates[]={"2026-02-30T11:00:00Z","2026-13-01T11:00:00Z","2026-10-31T25:00:00Z","2026-10-31T11:60:00Z","2026-10-31T11:00:60Z","2026-10-31 11:00:00Z","2026-10-31T11:00:00+00:00","2019-12-31T23:59:59Z"};
 for(unsigned i=0;i<sizeof(dates)/sizeof(*dates);++i){init();arm();process(frame("x",event,"STOP_BUZZER",dates[i]),utc);assert(!command_processor_ack_pending()&&on);}
 init();arm();mqtt_manager_command_t f=valid;f.length=513;process(f,utc);assert(!command_processor_ack_pending());
 f=valid;f.payload[4]=0;process(f,utc);assert(!command_processor_ack_pending());
 f=frame("bad\"id",event,"STOP_BUZZER","2026-10-31T11:00:00Z");process(f,utc);assert(!command_processor_ack_pending());
 init();arm();command_processor_tick(41000000);assert(!on&&stop_calls==1); /* independent local failsafe */
 assert(command_processor_arm_test(event,42000000)!=ESP_OK); /* never reuse active event */
 init();arm();fail_stop=true;command_processor_tick(41000000);assert(on);fail_stop=false;command_processor_tick(42000000);assert(!on);
 init();fail_on=true;assert(command_processor_arm_test(event,11000000)!=ESP_OK);
 init();fail_read=true;assert(command_processor_arm_test(event,11000000)!=ESP_OK);
 init();arm();assert(command_processor_arm_test("223e4567-e89b-42d3-a456-426614174000",12000000)!=ESP_OK);
 init();for(unsigned i=0;i<17;i++){char id[16];snprintf(id,sizeof(id),"id-%u",i);process(frame(id,event,"STOP_BUZZER","2026-10-31T11:00:00Z"),utc);command_processor_ack_queued();}expect("REJECTED","EVENT_NOT_ACTIVE");
 command_processor_init(false);process(valid,utc);assert(!command_processor_ack_pending());assert(command_processor_arm_test(event,11000000)!=ESP_OK);
 puts("command processor scenarios PASS (fake actuator, not hardware)");return 0;
}
