"""Bounded real-board reliability recorder with local control file.

Only whitelisted serial diagnostics are accepted. Broker stop/start and AP
operations are performed separately so the evidence records the actual fault.
No mock, no credentials on stdout, no Backend/App claim.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid
import serial

ROOT=Path(__file__).resolve().parents[1]
CONTAINER='fall-phase3-broker'
ALLOWED={'TEST_ALERT','TEST_ALERT_BUZZER','TEST_MOTOR','TEST_PUBLISH_OFFLINE','TEST_WIFI_DROP'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',default='COM5')
    p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--duration',type=int,default=1200)
    p.add_argument('--reset',action='store_true')
    p.add_argument('--observe-command',action='store_true',help='Phase7: passively capture command topic; never publish commands')
    args=p.parse_args()
    if not 1<=args.duration<=1800:raise RuntimeError('Duration must be 1..1800 seconds')
    out=args.out_dir;out.mkdir(parents=True,exist_ok=True)
    if (out/'runtime.log').exists():raise RuntimeError('Use a new output directory')
    s=json.loads((ROOT/'build/phase8_2_3/broker/client_secrets.json').read_text())
    base='iot/devices/'+s['deviceId'];auth=['-u',s['backendUsername'],'-P',s['backendPassword']]
    identity='phase6-probe-'+uuid.uuid4().hex;pidfile='/tmp/'+identity+'.pid'
    port=serial.Serial(port=None,baudrate=115200,timeout=.2);port.dtr=port.rts=False;port.port=args.port
    raw=bytearray();frames=[];actions=[];errors=[];done=threading.Event();started=time.monotonic();proc=None
    def capture():
        try:
            with (out/'runtime.log').open('xb') as f:
                while not done.is_set():
                    chunk=port.read(min(max(port.in_waiting,1),8192));raw.extend(chunk);f.write(chunk);f.flush()
        except Exception:errors.append('Serial read failed')
    def start_subscriber():
        command_topics=['-t',base+'/command'] if args.observe_command else []
        child=subprocess.Popen(['docker','exec',CONTAINER,'sh','-c','echo $$ > "$1"; shift; exec "$@"','phase6',pidfile,
                'mosquitto_sub','-h','127.0.0.1','-i',identity,'-W','1800',*auth,'-t',base+'/status','-t',base+'/event',*command_topics,'-q','1','-F','%r %q %t %p'],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
        def reader():
            with (out/'mqtt_frames.jsonl').open('a',encoding='utf-8') as f:
                for line in child.stdout:
                    try:
                        retain,qos,topic,payload=line.strip().split(' ',3)
                        item=dict(elapsed_s=round(time.monotonic()-started,3),retain=int(retain),qos=int(qos),topic=topic,payload=json.loads(payload))
                        frames.append(item);f.write(json.dumps(item)+'\n');f.flush()
                    except ValueError:errors.append('Invalid MQTT JSON/format')
        threading.Thread(target=reader,daemon=True).start();return child
    def summary():
        t=re.sub(r'\x1b\[[0-9;]*m','',bytes(raw).decode('utf-8','replace'));lines=t.splitlines()
        diag=[l for l in lines if 'SENSOR_MANAGER: diag_5s' in l];jitter=[l for l in lines if 'diag_jitter' in l]
        def values(pattern,ls):return [int(m[1]) for l in ls if (m:=re.search(pattern,l))]
        heap=[{k:int(v) for k,v in re.findall(r'(free_internal|min_internal|largest_internal|free_8bit|tasks|stack_min)=(\d+)',l)} for l in lines if 'DEVICE_TELEMETRY: resources' in l]
        mqtt=[l for l in lines if 'MQTT_MANAGER: resources' in l]
        events=[f for f in frames if f['topic'].endswith('/event')]
        return dict(elapsed_s=round(time.monotonic()-started,2),bytes=len(raw),diag_windows=len(diag),
                got_ip=t.count('WIFI_MANAGER: GOT_IP'),wifi_offline=t.count('WIFI_MANAGER: offline;'),
                mqtt_connections=t.count('MQTT_MANAGER: connected:'),subacks=t.count('SUBACK confirmed:'),
                missed_ticks_max=max(values(r'missed_ticks=(\d+)',diag),default=0),
                imu_err_max=max(values(r'imu_err=(\d+)',diag),default=0),bmp_err_max=max(values(r'bmp_err=(\d+)',jitter),default=0),
                outliers_max=max(values(r' outliers=(\d+)',jitter),default=0),diag_dropped_max=max(values(r'diag_dropped=(\d+)',jitter),default=0),
                gap_min_us=min(values(r'gap_us\[min/avg/max\]=(\d+)/',diag),default=None),
                gap_max_us=max(values(r'gap_us\[min/avg/max\]=\d+/\d+/(\d+)',diag),default=None),
                last_diag=diag[-1:] ,latest_heap=heap[-1:] ,heap_samples=len(heap),latest_mqtt_resources=mqtt[-1:],
                events=len(events),unique_event_ids=len({f['payload'].get('eventId') for f in events}),
                motor_on=t.count('MOTOR_TEST ON requested'),motor_off=t.count('MOTOR_TEST OFF requested'),
                auto_off=t.count('TEST_BUZZER_TIMEOUT off_result=0'),stops=t.count('STOP_BUZZER EXECUTED commandId='),
                button_presses=t.count('matches_configured_active=1 diagnostic_only=1'),
                offline_publish_rejected=t.count('expected_offline_rejection=1'),csv_finished='CSV_EXPORT_FINISHED' in t,
                reset_count=t.count('rst:0x'),fatal=any(x in t for x in ['Guru Meditation','panic_abort','Brownout detector','assert failed','TG1WDT_SYS_RST','TG0WDT_SYS_RST']),
                collector_errors=errors)
    try:
        port.open();port.reset_input_buffer()
        if args.reset:port.rts=True;time.sleep(.1);port.rts=False
        worker=threading.Thread(target=capture,daemon=True);worker.start()
        next_sub=next_report=0
        while time.monotonic()-started<args.duration and not (out/'stop').exists():
            now=time.monotonic()-started
            if (proc is None or proc.poll() is not None) and now>=next_sub:
                proc=start_subscriber();next_sub=now+3
            control=out/'control.json'
            if control.exists():
                try:item=json.loads(control.read_text())
                except (json.JSONDecodeError,PermissionError):time.sleep(.05);continue
                command=item.get('serial')
                if command not in ALLOWED:raise RuntimeError('Control file command not allowed')
                port.write((command+'\n').encode('ascii'));control.unlink()
                actions.append(dict(elapsed_s=round(now,3),serial=command))
                (out/'actions.json').write_text(json.dumps(actions,indent=2))
                print('Serial diagnostic sent: '+command,flush=True)
            if now>=next_report:
                result=summary();(out/'status.json').write_text(json.dumps(result,indent=2))
                if int(now)%30<2:print(json.dumps({k:result[k] for k in ['elapsed_s','got_ip','subacks','missed_ticks_max','outliers_max','latest_heap']}),flush=True)
                if result['fatal'] or errors:break
                next_report=now+2
            time.sleep(.2)
    finally:
        done.set()
        if 'worker' in locals():worker.join(timeout=2)
        if port.is_open:port.close()
        subprocess.run(['docker','exec',CONTAINER,'sh','-c','if test -r "$1"; then read -r p < "$1"; if test -r "/proc/$p/cmdline" && grep -q "$2" "/proc/$p/cmdline"; then kill -TERM "$p"; fi; rm -f "$1"; fi','phase6-cleanup',pidfile,identity],capture_output=True,timeout=10)
        if proc:
            try:proc.wait(timeout=3)
            except subprocess.TimeoutExpired:proc.terminate()
        result=summary();result['raw_sha256']=hashlib.sha256(raw).hexdigest()
        (out/'status.json').write_text(json.dumps(result,indent=2));(out/'mqtt_frames.json').write_text(json.dumps(frames,indent=2))
        print(json.dumps(result),flush=True)

if __name__=='__main__':main()
