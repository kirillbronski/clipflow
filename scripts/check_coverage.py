"""Coverage gates include all own runtime modules, even child-only modules."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'work/verification'


def fingerprint():
    digest=hashlib.sha256()
    for path in sorted((ROOT/'src/clipflow').rglob('*.py')):
        digest.update(str(path.relative_to(ROOT)).replace('\\','/').encode()); digest.update(path.read_bytes())
    return digest.hexdigest()


def evaluate(report):
    core={key:0 for key in ('covered_lines','num_statements','covered_branches','num_branches')}
    total=dict(core)
    for path,entry in report['files'].items():
        path=path.replace('\\','/')
        for key in total:
            value=entry['summary'].get(key,0)
            total[key]+=value
            if '/domain/' in path or '/application/' in path: core[key]+=value
    def ratio(data,part,whole): return data[part]/data[whole] if data[whole] else 0
    limits={'core_lines':(ratio(core,'covered_lines','num_statements'),.95),
            'core_branches':(ratio(core,'covered_branches','num_branches'),.90),
            'runtime_lines':(ratio(total,'covered_lines','num_statements'),.85)}
    return {'passed':all(value>=minimum for value,minimum in limits.values()),
            'thresholds':{key:{'value':value,'minimum':minimum,'passed':value>=minimum}
                          for key,(value,minimum) in limits.items()},'core':core,'runtime':total}


def run():
    from coverage import Coverage
    OUTPUT.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='clipflow-qt-check-') as isolated:
        result=subprocess.run([sys.executable,'-m','pytest','--cov=src/clipflow','--cov-report=',
            '--cov-config='+str(ROOT/'pyproject.toml')],cwd=ROOT,
            env=dict(os.environ,CLIPFLOW_DATA_DIR=isolated),timeout=360)
    if result.returncode: return result.returncode
    coverage=Coverage(config_file=str(ROOT/'pyproject.toml')); coverage.load()
    coverage.json_report(morfs=[str(p) for p in (ROOT/'src/clipflow').rglob('*.py')],outfile=str(OUTPUT/'coverage.json'))
    return check()


def check():
    result=evaluate(json.loads((OUTPUT/'coverage.json').read_text(encoding='utf-8')))
    result['source_fingerprint']=fingerprint()
    (OUTPUT/'coverage-gates.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    for name,gate in result['thresholds'].items():
        print(f'{name}: {gate["value"]:.2%} >= {gate["minimum"]:.0%}: {"PASS" if gate["passed"] else "FAIL"}')
    return 0 if result['passed'] else 1


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--reuse',action='store_true')
    args=parser.parse_args(argv)
    if args.reuse:
        previous=json.loads((OUTPUT/'coverage-gates.json').read_text(encoding='utf-8'))
        if previous.get('source_fingerprint')!=fingerprint(): raise SystemExit('Coverage is stale; run scripts/check.py --qt')
        return check()
    return run()


if __name__=='__main__': raise SystemExit(main())
