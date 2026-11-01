"""Guard against confusing MQTT/fixture evidence with a real end-to-end PASS."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import phase7_check_capture as subject

DEVICE = 'waist-esp32s3-001'
EVENT = '123e4567-e89b-42d3-a456-426614174000'
BASE = 'iot/devices/' + DEVICE


def fixture():
    raw = ('I (798) app_init: ELF file SHA256:  1840d338d...\nSUBACK confirmed:\n'
           f'TEST_ALERT requested: eventId={EVENT} isTest=true\n').encode()
    summary = dict(raw_sha256=hashlib.sha256(raw).hexdigest(), reset_count=1,
                   fatal=False, collector_errors=[], diag_windows=2,
                   missed_ticks_max=0, imu_err_max=0, bmp_err_max=0,
                   outliers_max=0, diag_dropped_max=0)
    status = dict(schemaVersion=1, deviceId=DEVICE, online=True, mode='REAL',
                  lteReady=False, alertState='IDLE', observedAt=None)
    event = dict(schemaVersion=1, deviceId=DEVICE, eventId=EVENT, eventType='TEST_ALERT',
                 isTest=True, occurredAt=None, modelVersion='firmware-test-v1', confidence=None,
                 location=dict(type='UNAVAILABLE', lat=None, lon=None, observedAt=None))
    frames = [dict(elapsed_s=1, retain=0, qos=1, topic=BASE+'/status', payload=status),
              dict(elapsed_s=2, retain=0, qos=1, topic=BASE+'/event', payload=event)]
    return summary, raw, frames


class CaptureTests(unittest.TestCase):
    def evaluate(self, change=None):
        s, raw, f = fixture()
        if change: change(s, f)
        return subject.evaluate(s, raw, f, DEVICE)

    def test_broker_pass_never_implies_e2e(self):
        r = self.evaluate()
        self.assertEqual(r['device_to_broker'], 'PASS')
        self.assertEqual(r['end_to_end'], 'NOT_VERIFIED')
        self.assertEqual(r['command_device_ack'], 'NOT_OBSERVED')

    def test_tampered_unfinished_or_crashed_capture(self):
        for key, value in [('raw_sha256', None), ('fatal', True), ('reset_count', 2),
                           ('collector_errors', ['serial failed']), ('diag_windows', 0),
                           ('missed_ticks_max', 1), ('outliers_max', 1)]:
            with self.subTest(key=key):
                self.assertEqual(self.evaluate(lambda s,f:s.update({key:value}))['device_to_broker'], 'INCOMPLETE_OR_FAILED')

    def test_missing_boot_and_trigger(self):
        s, raw, f = fixture()
        raw=b'not a board log';s['raw_sha256']=hashlib.sha256(raw).hexdigest()
        self.assertEqual(subject.evaluate(s,raw,f,DEVICE)['device_to_broker'],'INCOMPLETE_OR_FAILED')

    def test_mock_retained_wrong_identity_and_qos(self):
        changes=[lambda s,f:f[0]['payload'].update(mode='MOCK'),
                 lambda s,f:f[0].update(retain=1), lambda s,f:f[0].update(qos=0),
                 lambda s,f:f[0]['payload'].update(deviceId='other'),
                 lambda s,f:f[0]['payload'].update(lteReady=True),
                 lambda s,f:f[0]['payload'].update(schemaVersion=True),
                 lambda s,f:f[0]['payload'].update(observedAt='yesterday')]
        for change in changes:
            self.assertNotEqual(self.evaluate(change)['device_to_broker'],'PASS')

    def test_event_safety_and_schema(self):
        changes=[dict(isTest=False),dict(isTest=1),dict(eventType='FALL_CONFIRMED'),
                 dict(deviceId='other'),dict(eventId='bad'),dict(occurredAt='bad'),
                 dict(modelVersion='invented-model'),dict(confidence=0.99)]
        for change in changes:
            self.assertNotEqual(self.evaluate(lambda s,f:f[1]['payload'].update(change))['device_to_broker'],'PASS')
        for change in [dict(retain=1),dict(qos=0),dict(topic=BASE+'/other')]:
            self.assertNotEqual(self.evaluate(lambda s,f:f[1].update(change))['device_to_broker'],'PASS')

    def test_location_truthful_nulls_and_ranges(self):
        self.assertNotEqual(self.evaluate(lambda s,f:f[1]['payload']['location'].update(lat=21))['device_to_broker'],'PASS')
        for lat,lon in [(91,0),(0,181),(True,0),(float('nan'),0)]:
            self.assertNotEqual(self.evaluate(lambda s,f:f[1]['payload'].update(location=dict(type='CURRENT',lat=lat,lon=lon,observedAt=None)))['device_to_broker'],'PASS')
        for kind in ['CURRENT','LAST_KNOWN']:
            self.assertEqual(self.evaluate(lambda s,f:f[1]['payload'].update(location=dict(type=kind,lat=21,lon=105,observedAt='2026-10-31T11:00:00Z')))['device_to_broker'],'PASS')

    def test_invalid_time_and_location_shape(self):
        for value in [False, '2026-02-30T00:00:00Z', '2026-10-31T11:00:00+07:00']:
            self.assertFalse(subject.utc(value))
        for value in [None, {}, {'type':'OTHER','lat':0,'lon':0,'observedAt':None}]:
            self.assertFalse(subject.location(value))

    def test_duplicates_and_no_external_claims(self):
        r=self.evaluate(lambda s,f:f.append(copy.deepcopy(f[1])))
        self.assertEqual(r['unique_event_ids'],[EVENT]);self.assertEqual(r['event_deliveries'],2)
        self.assertEqual(r['backend_receive'],'NOT_VERIFIED')

    def test_command_ack_requires_observed_command_and_serial_execution(self):
        s,raw,f=fixture()
        command=dict(commandId='cmd-1',eventId=EVENT,command='STOP_BUZZER',issuedAt='2026-10-31T11:00:00Z')
        ack=dict(command, result='EXECUTED',reason='STOPPED',processedAt='2026-10-31T11:00:01Z');ack.pop('issuedAt')
        f[0]['payload']['lastCommand']=ack
        self.assertEqual(subject.evaluate(s,raw,f,DEVICE)['command_device_ack'],'NOT_OBSERVED')
        f.append(dict(topic=BASE+'/command',retain=0,qos=1,payload=command))
        self.assertEqual(subject.evaluate(s,raw,f,DEVICE)['command_device_ack'],'INCOMPLETE_OR_FAILED')
        raw+=f'STOP_BUZZER EXECUTED commandId=cmd-1 eventId={EVENT}; output verified off; event retained\n'.encode()
        s['raw_sha256']=hashlib.sha256(raw).hexdigest()
        self.assertEqual(subject.evaluate(s,raw,f,DEVICE)['command_device_ack'],'PASS')
        for key,value in [('result','ACK_SIMULATED'),('eventId','other'),('command','OTHER'),('processedAt',None)]:
            altered=copy.deepcopy(f);altered[0]['payload']['lastCommand'][key]=value
            self.assertNotEqual(subject.evaluate(s,raw,altered,DEVICE)['command_device_ack'],'PASS')
        for key,value in [('retain',1),('qos',0)]:
            altered=copy.deepcopy(f);altered[0][key]=value
            self.assertNotEqual(subject.evaluate(s,raw,altered,DEVICE)['command_device_ack'],'PASS')
        self.assertEqual(subject.evaluate(s,raw,f,DEVICE)['end_to_end'],'NOT_VERIFIED')

    def test_cli_reports_preserve_raw_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);s,raw,f=fixture()
            (d/'runtime.log').write_bytes(raw)
            (d/'status.json').write_text(json.dumps(s));(d/'mqtt_frames.json').write_text(json.dumps(f))
            self.assertEqual(subject.main([str(d),'--device-id',DEVICE]),0)
            self.assertEqual(subject.main([str(d),'--device-id',DEVICE]),0)
            self.assertEqual((d/'runtime.log').read_bytes(),raw)
            self.assertEqual(subject.main([str(d),'--require-command']),1)
            self.assertEqual(subject.main([str(d),'--device-id','bad/+#']),2)
            (d/'status.json').write_text('{}')
            self.assertEqual(subject.main([str(d),'--device-id',DEVICE]),1)
            (d/'mqtt_frames.json').write_text('{}')
            self.assertEqual(subject.main([str(d),'--device-id',DEVICE]),1)
            (d/'status.json').unlink()
            self.assertEqual(subject.main([str(d),'--device-id',DEVICE]),1)


if __name__=='__main__':unittest.main()
