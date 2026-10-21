"""Only assertion failures count as detected production regressions."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from .evidence import ROOT,manifest

MUTATIONS=[
    ('stale-incarnation',"require(p['incarnation'] == s['agents'].get(a['token']['node']), 'Stale incarnation')","require(True, 'Stale incarnation')",'test_old_incarnation_cannot_settle'),
    ('wrong-canary-data',"require(p['challenge'] == a['challenge'] and p['result'] == p['input'] * 2, 'Bad canary')","require(p['challenge'] == a['challenge'], 'Bad canary')",'test_duplicate_and_wrong_data_are_rejected'),
    ('expired-challenge',"require(0 <= now - a['challenge_ns'] <= 2_000_000_000, 'Expired sample challenge')","require(True, 'Expired sample challenge')",'test_expired_challenge_rejected'),
    ('commit-bypass',"require(a['commit_authorized'], 'Commit was not authorized')","require(True, 'Commit was not authorized')",'test_commit_cannot_bypass_controller_observation'),
    ('forget-reconciliation',"s['active']['needs_reconcile'] = True","s['active']['needs_reconcile'] = False",'test_restart_requires_reconciliation_and_resets_evidence')]


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();rows=[]
    for name,old,new,test in MUTATIONS:
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for folder in ('fleetweft','tests'):shutil.copytree(ROOT/folder,root/folder,ignore=shutil.ignore_patterns('__pycache__'))
            path=root/'fleetweft/core.py';text=path.read_text();assert text.count(old)==1;path.write_text(text.replace(old,new))
            result=subprocess.run([sys.executable,'-m','unittest','tests.test_core.Contracts.'+test],cwd=root,capture_output=True,text=True,timeout=10)
            caught=result.returncode==1 and 'FAIL:' in result.stderr and 'ERROR:' not in result.stderr
            rows.append({'name':name,'test':test,'caught_by_assertion':caught,'exit_code':result.returncode})
    value={'passed':all(r['caught_by_assertion'] for r in rows),'rows':rows,'source':manifest()}
    output=Path(a.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps({'passed':value['passed'],'mutations':len(rows)}));raise SystemExit(0 if value['passed'] else 1)


if __name__=='__main__':main()
