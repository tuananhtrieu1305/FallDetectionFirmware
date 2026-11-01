"""Real ESP32 demo STOP_BUZZER test. Sounds GPIO6 twice (30 s auto-off).

Requires local command/serial opt-ins, demo broker and a usable UTC source.
No AI fall, mock ACK, real rescue or Backend/App claim. Do not run a monitor
holding COM5. Credentials are loaded from ignored broker config and not printed.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid
import serial
from test_phase4_device import run_client

ROOT=Path(__file__).resolve().parents[1]
CONTAINER='fall-phase3-broker'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',default='COM5')
    parser.add_argument('--out-dir',type=Path,default=ROOT/'build/phase8_2_5/hardware')
    args=parser.parse_args();out=args.out_dir;out.mkdir(parents=True,exist_ok=True)
    if (out/'runtime.log').exists():raise RuntimeError('Choose a new output directory')
    secrets=json.loads((ROOT/'build/phase8_2_3/broker/client_secrets.json').read_text())
    base='iot/devices/'+secrets['deviceId'];auth=['-u',secrets['backendUsername'],'-P',secrets['backendPassword']]
    client='phase5-probe-'+uuid.uuid4().hex;pidfile='/tmp/'+client+'.pid'
    raw=bytearray();frames=[];errors=[];done=threading.Event();start=time.monotonic()
    port=serial.Serial(port=None,baudrate=115200,timeout=.2);port.dtr=port.rts=False;port.port=args.port
    def text():return re.sub(r'\x1b\[[0-9;]*m','',bytes(raw).decode('utf-8','replace'))
    def capture():
        try:
            with (out/'runtime.log').open('xb') as handle:
                while not done.is_set():
                    data=port.read(min(max(port.in_waiting,1),8192));raw.extend(data);handle.write(data);handle.flush()
        except Exception:errors.append('Serial capture failed')
    def read_mqtt():
        for line in subscriber.stdout:
            try:
                retain,qos,topic,payload=line.strip().split(' ',3)
                frames.append(dict(elapsed_s=round(time.monotonic()-start,3),retain=int(retain),qos=int(qos),topic=topic,payload=json.loads(payload)))
            except ValueError:errors.append('MQTT JSON/format invalid')
    def wait(predicate,seconds,label):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if errors:raise RuntimeError(errors[0])
            if any(s in text() for s in ['Guru Meditation','panic_abort','assert failed','Brownout detector']):raise RuntimeError('Firmware fatal error')
            if predicate():print(label+': PASS',flush=True);return
            time.sleep(.2)
        raise RuntimeError(label+': timeout; inspect runtime/MQTT frames')
    def observe(seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if errors:raise RuntimeError(errors[0])
            time.sleep(.2)
    def events():return [f['payload'] for f in frames if f['topic']==base+'/event']
    def stamp(delta=0):return (datetime.now(timezone.utc)+timedelta(seconds=delta)).strftime('%Y-%m-%dT%H:%M:%SZ')
    def publish(payload):
        data=payload.encode('ascii') if isinstance(payload,str) else json.dumps(payload,separators=(',',':')).encode('ascii')
        r=run_client(['docker','exec','-i',CONTAINER,'mosquitto_pub','-h','127.0.0.1',*auth,'-t',base+'/command','-q','1','-s'],input=data,capture_output=True,timeout=10)
        if r.returncode:raise RuntimeError('Command publisher failed; credentials omitted')
    def command(event_id,delta=0,name='STOP_BUZZER'):
        return dict(commandId=str(uuid.uuid4()),eventId=event_id,command=name,issuedAt=stamp(delta))
    def ack(cmd,result,reason,after=0):
        def matching():return [f for f in frames[after:] if f['topic']==base+'/status' and f['retain']==0
                              and f['payload'].get('lastCommand',{}).get('commandId')==cmd['commandId']
                              and f['payload']['lastCommand'].get('result')==result and f['payload']['lastCommand'].get('reason')==reason]
        wait(lambda:bool(matching()),8,result+'/'+reason)
        return matching()[-1]['payload']
    def send_expect(cmd,result,reason,on):
        mark=len(frames);publish(cmd);status=ack(cmd,result,reason,mark)
        assert status['alertState']==('BUZZER_ON' if on else 'IDLE')
        assert status['lastCommand']['eventId']==cmd['eventId'];return status['lastCommand']
    def arm():
        before=len(events());port.write(b'TEST_ALERT_BUZZER\n')
        wait(lambda:len(events())==before+1,10,'Explicit buzzer TEST_ALERT received')
        event=events()[-1];event_id=event['eventId']
        wait(lambda:'TEST_BUZZER_ARMED eventId='+event_id in text() and any(f['payload'].get('alertState')=='BUZZER_ON' and f['elapsed_s']>time.monotonic()-start-2 for f in frames if f['topic']==base+'/status'),5,'Physical LEDC output on')
        return event_id
    subscriber=None
    try:
        port.open()
        subscriber=subprocess.Popen(['docker','exec',CONTAINER,'sh','-c','echo $$ > "$1"; shift; exec "$@"','phase5',pidfile,
                                     'mosquitto_sub','-h','127.0.0.1','-i',client,'-W','240',*auth,'-t',base+'/status','-t',base+'/event','-q','1','-F','%r %q %t %p'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
        reader=threading.Thread(target=read_mqtt,daemon=True);reader.start()
        capturer=threading.Thread(target=capture,daemon=True);capturer.start();observe(1)
        port.rts=True;time.sleep(.1);port.rts=False
        wait(lambda:'SUBACK confirmed:' in text(),30,'ESP32 MQTT SUBACK')
        wait(lambda:any(f['payload'].get('online') is True and f['payload'].get('observedAt') is not None and f['retain']==0 for f in frames if f['topic']==base+'/status'),100,'Actual UTC source ready')
        wait(lambda:time.monotonic()-start>=13,20,'Boot diagnostics settled')
        assert not events(),'Automatic event at boot'
        print('BUZZER TEST STARTING: local arm, then real MQTT STOP; auto-off 30 s',flush=True)
        first=arm()
        # Malformed/extra-target JSON must not create a result or turn it off.
        publish('{"commandId":"x","eventId":"'+first+'","command":"STOP_BUZZER","issuedAt":"'+stamp()+'","deviceId":"wrong-device"}')
        observe(1);assert 'STOP_BUZZER EXECUTED' not in text()
        send_expect(command(first,-60),'REJECTED','EXPIRED',True)
        send_expect(command(first,60),'REJECTED','FUTURE_ISSUED_AT',True)
        send_expect(command(str(uuid.uuid4())),'REJECTED','EVENT_NOT_ACTIVE',True)
        send_expect(command(first,name='START_BUZZER'),'REJECTED','UNSUPPORTED_COMMAND',True)
        stop=command(first);original=send_expect(stop,'EXECUTED','STOPPED',False)
        cached=send_expect(stop,'EXECUTED','STOPPED',False);assert cached==original
        wait(lambda:'duplicate commandId='+stop['commandId'] in text(),3,'Duplicate did not execute actuator')
        reused=dict(stop);reused['issuedAt']=stamp(1);send_expect(reused,'REJECTED','COMMAND_ID_REUSED',False)
        send_expect(command(first),'REJECTED','NOT_BUZZING',False) # event remains active, not cancelled
        observe(5)
        second=arm();assert second!=first
        # Cached success relates to old event; must leave new buzzer ON.
        old=send_expect(stop,'EXECUTED','STOPPED',True);assert old==original
        send_expect(command(first),'REJECTED','EVENT_NOT_ACTIVE',True)
        second_stop=command(second);send_expect(second_stop,'EXECUTED','STOPPED',False)
        # Ensure no unrequested test event and status/ACK survives MQTT recovery.
        subprocess.run(['docker','stop',CONTAINER],capture_output=True,timeout=20)
        observe(5)
        subprocess.run(['docker','start',CONTAINER],capture_output=True,timeout=20)
        # The subscriber exec ended with the container. Start another bounded one.
        try:subscriber.wait(timeout=10)
        except subprocess.TimeoutExpired:raise RuntimeError('Subscriber did not stop with broker; credentials omitted') from None
        subscriber=subprocess.Popen(['docker','exec',CONTAINER,'sh','-c','echo $$ > "$1"; shift; exec "$@"','phase5',pidfile,
                                     'mosquitto_sub','-h','127.0.0.1','-i',client,'-W','180',*auth,'-t',base+'/status','-t',base+'/event','-q','1','-F','%r %q %t %p'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
        threading.Thread(target=read_mqtt,daemon=True).start()
        wait(lambda:text().count('SUBACK confirmed:')>=2,30,'MQTT reconnect')
        send_expect(second_stop,'EXECUTED','STOPPED',False)
        observe(6);assert len(events())==2,'Reconnect generated an event'
        port.write(b'TEST_ALERT\n');wait(lambda:len(events())==3,10,'Plain Phase 4 TEST_ALERT remains available')
        assert text().count('TEST_BUZZER_ARMED eventId=')==2
        wait(lambda:'CSV_EXPORT_FINISHED' in text(),100,'CSV export completed')
        observe(8)
        assert text().count('STOP_BUZZER EXECUTED commandId=')==2
        diag=[l for l in text().splitlines() if 'diag_5s' in l];jitter=[l for l in text().splitlines() if 'diag_jitter' in l]
        assert len(diag)>=12
        for line in diag:assert 'imu_err=0' in line and 'missed_ticks=0' in line
        for line in jitter:assert all(k+'=0' in line for k in ['bmp_err','outliers','diag_dropped'])
        for event in events():assert event['eventType']=='TEST_ALERT' and event['isTest'] is True
        for f in frames:
            if 'lastCommand' in f['payload']:
                a=f['payload']['lastCommand'];assert a['result'] in ['EXECUTED','REJECTED','FAILED']
                if a['result']=='EXECUTED':assert a['processedAt'] is not None
        report=dict(phase='8.2.5',electrical_hardware_verified=True,acoustic_confirmation='PENDING_USER',
                    duration_s=round(time.monotonic()-start,2),events=3,executed_stops=2,
                    duplicate_no_reexecution=True,event_context_retained=True,negative_commands_rejected=True,
                    diag_windows=len(diag),command_ids=[stop['commandId'],second_stop['commandId']])
        (out/'results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
    finally:
        done.set()
        if 'capturer' in locals():capturer.join(timeout=2)
        if port.is_open:port.close()
        subprocess.run(['docker','start',CONTAINER],capture_output=True,timeout=20)
        if subscriber:
            subprocess.run(['docker','exec',CONTAINER,'sh','-c','if test -r "$1"; then read -r p < "$1"; if test -r "/proc/$p/cmdline" && grep -q "$2" "/proc/$p/cmdline"; then kill -TERM "$p"; fi; rm -f "$1"; fi','phase5-cleanup',pidfile,client],capture_output=True,timeout=10)
            try:subscriber.wait(timeout=3)
            except subprocess.TimeoutExpired:subscriber.terminate()
        (out/'mqtt_frames.json').write_text(json.dumps(frames,indent=2))
        if (out/'runtime.log').exists():(out/'runtime.sha256').write_text(hashlib.sha256((out/'runtime.log').read_bytes()).hexdigest())

if __name__=='__main__':main()
