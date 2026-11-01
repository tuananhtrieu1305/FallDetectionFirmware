"""Verify a completed Phase 6 capture; never turn missing evidence into PASS."""
import argparse
import hashlib
import json
from pathlib import Path
import re

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture_dir',type=Path);p.add_argument('--min-duration',type=int,default=900);p.add_argument('--network-capture',type=Path)
    a=p.parse_args();d=a.capture_dir;s=json.loads((d/'status.json').read_text());t=(d/'runtime.log').read_text(errors='replace')
    checks={}
    def check(name,ok):checks[name]=bool(ok)
    def raw_complete(directory,summary):
        return summary.get('raw_sha256') == hashlib.sha256((directory/'runtime.log').read_bytes()).hexdigest()
    check('capture_closed_and_hash_verified',raw_complete(d,s))
    if not checks['capture_closed_and_hash_verified']:
        raise SystemExit('INCOMPLETE: capture is still running or raw SHA-256 does not match')
    check('duration',s['elapsed_s']>=a.min_duration)
    check('sensor_no_errors',all(s[k]==0 for k in ['missed_ticks_max','imu_err_max','bmp_err_max','outliers_max','diag_dropped_max']))
    check('no_crash_or_reset',not s['fatal'] and s['reset_count']==1 and not s['collector_errors'])
    check('wifi_recovery',s['wifi_offline']>=1 and s['got_ip']>=2)
    check('mqtt_multiple_recovery',s['subacks']>=4)
    network=None
    if a.network_capture:
        network=json.loads((a.network_capture/'status.json').read_text());nt=(a.network_capture/'runtime.log').read_text(errors='replace')
        check('network_capture_closed_and_hash_verified',raw_complete(a.network_capture,network))
        if not checks['network_capture_closed_and_hash_verified']:
            raise SystemExit('INCOMPLETE: network capture is still running or raw SHA-256 does not match')
        check('targeted_network_duration',network['elapsed_s']>=180)
        check('targeted_network_no_faults',not network['fatal'] and network['reset_count']==1 and not network['collector_errors'] and all(network[k]==0 for k in ['missed_ticks_max','imu_err_max','bmp_err_max','outliers_max','diag_dropped_max']))
        check('wifi_recovery',network['wifi_offline']>=2 and network['got_ip']>=3 and network['subacks']>=3 and nt.count('WIFI_DROP_TEST SDK disconnect result=0')>=2)
        check('mqtt_multiple_recovery',s['subacks']+network['subacks']>=4)
        t+='\n'+nt
    check('offline_publish_failure',s['offline_publish_rejected']>=2)
    check('motor_pair',s['motor_on']>=1 and s['motor_off']==s['motor_on'])
    check('button_transitions',s['button_presses']>=5)
    check('local_auto_off',s['auto_off']>=1)
    check('real_stop',s['stops']>=1)
    check('csv_complete',s['csv_finished'])
    heap=[];mqtt=[]
    for line in t.splitlines():
        ts=re.search(r'\((\d+)\)',line)
        if 'DEVICE_TELEMETRY: resources' in line:
            fields={k:int(v) for k,v in re.findall(r'(free_internal|min_internal|largest_internal|free_8bit|tasks|stack_min)=(\d+)',line)}
            if len(fields)==6:fields['uptime_ms']=int(ts[1]) if ts else 0;heap.append(fields)
        if 'MQTT_MANAGER: resources' in line:
            m=re.search(r'rx_queue=(\d+)/4 tx_queue=(\d+)/4 outbox_bytes=(\d+) stack_min=(\d+) pub_ok=(\d+) pub_fail=(\d+) tx_drop=(\d+)',line)
            if m:mqtt.append(tuple(map(int,m.groups())))
    check('resource_samples',len(heap)>=30 and bool(mqtt))
    check('queue_bounds',bool(mqtt) and all(x[0]<=4 and x[1]<=4 and x[2]<=8320 for x in mqtt))
    check('stacks',bool(heap) and bool(mqtt) and min(x['stack_min'] for x in heap)>=1024 and min(x[3] for x in mqtt)>=1024)
    steady=[x for x in heap if x['uptime_ms']>=120000]
    if len(steady)>=10:
        first=min(x['free_internal'] for x in steady[:5]);last=min(x['free_internal'] for x in steady[-5:])
        check('heap_tail_within_2KiB',last>=first-2048)
    else:first=last=None;check('heap_tail_within_2KiB',False)
    check('bounded_tasks',bool(heap) and max(x['tasks'] for x in heap)<=20)
    drops=[int(x) for x in re.findall(r'command frame queued: received=\d+ dropped=(\d+)',t)]
    check('rx_full_fault_seen',bool(drops) and max(drops)>0)
    check('gnss_parser_running','GNSS SELFTEST PASS' in t and bool(re.search(r'parsed RMC/GGA=[1-9]\d*',t)))
    check('lte_safe','UART disabled, no AT commands' in t and 'AT RESPONSE PASS' not in t)
    frames=json.loads((d/'mqtt_frames.json').read_text())
    if a.network_capture:frames+=json.loads((a.network_capture/'mqtt_frames.json').read_text())
    events=[f for f in frames if f['topic'].endswith('/event')]
    check('event_safety',bool(events) and all(f['payload'].get('isTest') is True and f['payload'].get('eventType')=='TEST_ALERT' for f in events))
    generated=t.count('TEST_ALERT requested:')
    check('no_unrequested_event_ids',len({f['payload']['eventId'] for f in events})==generated)
    check('cached_duplicate_seen','cached result, no actuator execution' in t)
    manual_path=d/'manual_evidence.json';manual=json.loads(manual_path.read_text()) if manual_path.exists() else {}
    check('manual_evidence',all(manual.get(k) is True for k in ['button_physical','motor_physical','auto_off_acoustic']))
    report=dict(phase='8.2.6',status='PASS' if all(checks.values()) else 'INCOMPLETE_OR_FAILED',checks=checks,
                duration_s=s['elapsed_s'],diag_windows=s['diag_windows'],gap_us=[s['gap_min_us'],s['gap_max_us']],
                heap_first_window_min=first,heap_last_window_min=last,heap_samples=len(heap),
                heap_min_internal=min((x['min_internal'] for x in heap),default=None),
                stack_min_telemetry=min((x['stack_min'] for x in heap),default=None),stack_min_mqtt=min((x[3] for x in mqtt),default=None),
                tasks_range=[min((x['tasks'] for x in heap),default=None),max((x['tasks'] for x in heap),default=None)],
                rx_dropped_max=max(drops,default=0),queue_outbox_max=[max((x[i] for x in mqtt),default=0) for i in range(3)],
                raw_sha256=s.get('raw_sha256'),network_capture=network,
                ap_power_outage_retested=manual.get('p101_toggled') is True)
    (d/'verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    if not all(checks.values()):raise SystemExit(1)

if __name__=='__main__':main()
