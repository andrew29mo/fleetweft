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
    ('fleetweft/core.py','stale-incarnation',"require(p['incarnation'] == s['agents'].get(a['token']['node']), 'Stale incarnation')","require(True, 'Stale incarnation')",'tests.test_core.Contracts.test_old_incarnation_cannot_settle'),
    ('fleetweft/core.py','wrong-canary-data',"require(p['challenge'] == a['challenge'] and p['result'] == p['input'] * 2, 'Bad canary')","require(p['challenge'] == a['challenge'], 'Bad canary')",'tests.test_core.Contracts.test_duplicate_and_wrong_data_are_rejected'),
    ('fleetweft/core.py','expired-challenge',"require(0 <= now - a['challenge_ns'] <= 2_000_000_000, 'Expired sample challenge')","require(True, 'Expired sample challenge')",'tests.test_core.Contracts.test_expired_challenge_rejected'),
    ('fleetweft/core.py','commit-bypass',"require(a['commit_authorized'], 'Commit was not authorized')","require(True, 'Commit was not authorized')",'tests.test_core.Contracts.test_commit_cannot_bypass_controller_observation'),
    ('fleetweft/core.py','forget-reconciliation',"s['active']['needs_reconcile'] = True","s['active']['needs_reconcile'] = False",'tests.test_core.Contracts.test_restart_requires_reconciliation_and_resets_evidence'),
    ('fleetweft/node.py','skip-request-drain',"while self.inflight.get(worker, 0) and time.monotonic() < deadline:","while False:",'tests.test_node_retirement.RetirementContracts.test_borrowed_request_finishes_before_worker_is_retired'),
    ('fleetweft/coordinator.py','fleet-canary-bypass',"([f['canary']] if f['mode']=='DEPLOY' and not f['canary_passed'] else ['a','b','c'])","['a','b','c']",'tests.test_mvp.FleetTests.test_canary_must_settle_before_other_nodes'),
    ('fleetweft/coordinator.py','lost-node-identity',"require(report['node_uuid']==r['node_uuid'],'Node state was lost or replaced')","require(True,'Node state was lost or replaced')",'tests.test_mvp.FleetTests.test_lost_node_state_rejected'),
    ('fleetweft/coordinator.py','restart-auto-resume',"s['paused']=True; s['fleet']['phase']='PAUSED'\n        self.store.save(s)","s['paused']=False; s['fleet']['phase']='PAUSED'\n        self.store.save(s)",'tests.test_mvp.FleetTests.test_controller_restart_requires_reconciliation'),
    ('fleetweft/artifacts.py','signature-bypass',"require(r.returncode==0, 'Invalid artifact signature')","require(True, 'Invalid artifact signature')",'tests.test_mvp.ArtifactTests.test_wrong_key_with_matching_digest_is_rejected'),
    ('fleetweft/coordinator.py','non-atomic-settlement',"finally: self.store=durable","finally:\n                self.store=durable\n                durable.save(buffer.read())",'tests.test_mvp.AtomicFleetTests.test_settlement_error_keeps_durable_grant')]


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();rows=[]
    for file,name,old,new,test in MUTATIONS:
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for folder in ('fleetweft','tests'):shutil.copytree(ROOT/folder,root/folder,ignore=shutil.ignore_patterns('__pycache__'))
            path=root/file;text=path.read_text();assert text.count(old)==1;path.write_text(text.replace(old,new))
            result=subprocess.run([sys.executable,'-m','unittest',test],cwd=root,capture_output=True,text=True,timeout=10)
            caught=result.returncode==1 and 'FAIL:' in result.stderr and 'ERROR:' not in result.stderr
            rows.append({'name':name,'test':test,'caught_by_assertion':caught,'exit_code':result.returncode})
    value={'passed':all(r['caught_by_assertion'] for r in rows),'rows':rows,'source':manifest()}
    output=Path(a.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps({'passed':value['passed'],'mutations':len(rows)}));raise SystemExit(0 if value['passed'] else 1)


if __name__=='__main__':main()
