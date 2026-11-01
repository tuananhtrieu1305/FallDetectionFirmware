"""Bounded demo command/queue probe while phase6_capture owns the serial port."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import time
import uuid
from test_phase4_device import run_client
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture-dir',type=Path,required=True)
    p.add_argument('--label',required=True);p.add_argument('--repeat',type=Path)
    p.add_argument('--expect',default='EXECUTED');p.add_argument('--reason',default='STOPPED')
    p.add_argument('--burst-invalid',action='store_true');a=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}',a.label):raise RuntimeError('Invalid label')
    s=json.loads((ROOT/'build/phase8_2_3/broker/client_secrets.json').read_text());base='iot/devices/'+s['deviceId']
    auth=['-u',s['backendUsername'],'-P',s['backendPassword']]
    def frames():
        values=[]
        if (a.capture_dir/'mqtt_frames.jsonl').exists():
            for line in (a.capture_dir/'mqtt_frames.jsonl').read_text().splitlines():
                try:values.append(json.loads(line))
                except ValueError:pass
        return values
    if a.burst_invalid:
        data=(b'{"invalid":true}\n')*32
        result=run_client(['docker','exec','-i','fall-phase3-broker','mosquitto_pub','-h','127.0.0.1',*auth,'-t',base+'/command','-q','1','-l'],input=data,capture_output=True,timeout=20)
        if result.returncode:raise RuntimeError('Burst publisher failed; credentials omitted')
        record=dict(invalid_frames_sent=32,hardware_outcome='inspect RX counters/log and recovery')
    else:
        before=frames();mark=len(before)
        if a.repeat:command=json.loads(a.repeat.read_text())['command']
        else:
            events=[f['payload'] for f in before if f['topic']==base+'/event']
            if not events:raise RuntimeError('No real event captured')
            command=dict(commandId=str(uuid.uuid4()),eventId=events[-1]['eventId'],command='STOP_BUZZER',issuedAt=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
        result=run_client(['docker','exec','-i','fall-phase3-broker','mosquitto_pub','-h','127.0.0.1',*auth,'-t',base+'/command','-q','1','-s'],input=json.dumps(command,separators=(',',':')).encode('ascii'),capture_output=True,timeout=10)
        if result.returncode:raise RuntimeError('Publisher failed; credentials omitted')
        record=None;deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            matched=[f for f in frames()[mark:] if f['topic']==base+'/status' and f['retain']==0 and f['payload'].get('lastCommand',{}).get('commandId')==command['commandId']]
            if matched:
                status=matched[-1]['payload'];ack=status['lastCommand']
                if ack['result']!=a.expect or ack['reason']!=a.reason:raise RuntimeError('Unexpected command result: '+ack['result']+'/'+ack['reason'])
                record=dict(command=command,ack=ack,status_alert_state=status.get('alertState'));break
            time.sleep(.2)
        if record is None:raise RuntimeError('ACK timeout; inspect broker/device evidence')
    (a.capture_dir/(a.label+'.json')).write_text(json.dumps(record,indent=2));print(json.dumps(record))

if __name__=='__main__':main()
