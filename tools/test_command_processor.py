"""Compile real parser/processor and bundled cJSON; fake actuator is not hardware."""
import gzip
import json
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def main():
    build = ROOT / 'build/phase8_2_5/host_tests'
    include = build / 'include'
    for name in ['esp_err.h', 'esp_log.h']:
        p = include / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('#include "host_sdk.h"\n')
    cjson = Path('C:/esp/v5.5.5/esp-idf/components/json/cJSON')
    cc = 'C:/msys64/ucrt64/bin/gcc.exe'
    flags = ['-std=gnu17', '-Wall', '-Wextra', '-Werror', '--coverage', '-I', str(include),
             '-I', str(ROOT/'tests/command_processor'), '-I', str(ROOT/'main'), '-I', str(cjson)]
    objects=[]
    for source in [ROOT/'main/command_processor.c', ROOT/'tests/command_processor/host_test.c',cjson/'cJSON.c']:
        obj=build/(source.stem+'.o');objects.append(str(obj))
        subprocess.run([cc,*flags,'-c',str(source),'-o',str(obj)],check=True)
        obj.with_suffix('.gcda').unlink(missing_ok=True)
    exe=build/'command_tests.exe'
    subprocess.run([cc,'--coverage',*objects,'-o',str(exe)],check=True)
    r=subprocess.run([str(exe)],capture_output=True,text=True,cwd=build)
    (build/'scenarios.log').write_text(r.stdout+r.stderr)
    assert r.returncode==0,r.stdout+r.stderr
    for line in r.stdout.splitlines():
        if line.startswith('ACK '):
            ack=json.loads(line[4:]);assert ack['result'] in ['EXECUTED','REJECTED','FAILED'];assert ack['result']!='ACK_SIMULATED'
    subprocess.run(['C:/msys64/ucrt64/bin/gcov.exe','--json-format','-o',str(build),str(ROOT/'main/command_processor.c')],check=True,cwd=build)
    data=json.loads(gzip.decompress((build/'command_processor.gcov.json.gz').read_bytes()))
    lines=next(f['lines'] for f in data['files'] if f['file'].replace('\\','/').endswith('/command_processor.c'))
    coverage=100*sum(l['count']>0 for l in lines)/len(lines)
    report=dict(status='PASS',line_coverage_percent=round(coverage,2),hardware_verified=False)
    (build/'results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report));assert coverage>=80

if __name__=='__main__':main()
