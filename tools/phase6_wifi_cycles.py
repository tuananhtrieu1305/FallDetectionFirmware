"""Drive bounded real SDK Wi-Fi faults via an existing serial recorder."""
import argparse
import json
from pathlib import Path
import time

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture_dir',type=Path)
    p.add_argument('--cycles',type=int,default=8);p.add_argument('--first-after',type=int,default=120)
    p.add_argument('--interval',type=int,default=35);a=p.parse_args()
    if not 1<=a.cycles<=12 or a.interval<20:raise RuntimeError('Invalid cycle bounds')
    d=a.capture_dir;records=[]
    def status():
        try:return json.loads((d/'status.json').read_text())
        except (FileNotFoundError,json.JSONDecodeError):return None
    def wait(predicate,timeout):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            s=status()
            if s:
                if s['fatal'] or s['reset_count']>1 or s['collector_errors']:raise RuntimeError('Firmware/capture fatal; inspect raw log')
                if predicate(s):return s
            time.sleep(.2)
        raise RuntimeError('Wi-Fi cycle timeout; inspect actual driver/recovery logs')
    try:
        for i in range(a.cycles):
            target=a.first_after+i*a.interval
            before=wait(lambda s:s['elapsed_s']>=target and s['subacks']>=1,180)
            # Reserve the slot exclusively. The recorder retries partial JSON;
            # replacing a checked path could overwrite a concurrent producer.
            try:
                with (d/'control.json').open('x') as control:
                    control.write('{"serial":"TEST_WIFI_DROP"}')
            except FileExistsError:
                raise RuntimeError('Another control action is pending; do not run concurrent producers') from None
            after=wait(lambda s:s['got_ip']>before['got_ip'] and s['subacks']>before['subacks'],30)
            record=dict(cycle=i+1,start_s=before['elapsed_s'],recovered_s=after['elapsed_s'],
                        got_ip=after['got_ip'],subacks=after['subacks'],missed_ticks=after['missed_ticks_max'],outliers=after['outliers_max'])
            records.append(record);(d/'wifi_cycles.json').write_text(json.dumps({'status':'RUNNING','cycles':records},indent=2));print(json.dumps(record),flush=True)
            if after['missed_ticks_max'] or after['outliers_max']:raise RuntimeError('Sampling regression during actual Wi-Fi recovery')
        (d/'wifi_cycles.json').write_text(json.dumps({'status':'PASS','cycles':records},indent=2));print('Wi-Fi fault cycles PASS',flush=True)
    except Exception as e:
        (d/'wifi_cycles.json').write_text(json.dumps({'status':'FAIL','cycles':records,'error':str(e)},indent=2))
        raise

if __name__=='__main__':main()
