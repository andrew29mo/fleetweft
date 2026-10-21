"""Fail-closed MVP evidence validation and deterministic HTML."""
import copy
import html
import json
import math
from .evidence import fingerprint
from fleetweft.store import require

CASES=('three-node-canary','failed-canary-pauses','startup-failure-restores','later-failure-partial-rollback','offline-latest-catch-up',
       'partition-retains-grant','agent-controller-sigkill','mtls-and-tampered-artifact','delayed-executor-real-backend','measured-requests')

def check(ok,reason): require(ok,reason)
def serving(row,release):
    check(set(row)==set('abc'),'Missing serving target')
    check(all(v['release']==release and v['route']['release']==release and v['result']==14 for v in row.values()),'Wrong serving result')

def verify(v,source):
    check(v['passed'] is True and v['source']==source and v['source_sha256']==fingerprint(source),'Wrong source')
    check(v['source_changed'] is False and v['vm_initial']=='Stopped' and v['vm_final']=='Stopped','VM/source lifecycle')
    check(v['snapshot_removed'] is True and all(v['cleanup'].get(k) is True for k in ('units_stopped','namespaces_removed','root_firewall_unchanged','credentials_removed')),'Cleanup incomplete')
    expected_stages=('native-unit','mutations','vm-initial','vm-start','preflight','wheel-build','upload','install','guest-setup','linux-unit','linux-unit-read','vm-orderly-stop','vm-between','vm-restart','guest-after-reboot','guest-cleanup','remove','vm-stop','vm-final')
    check(tuple(s['name'] for s in v['stages'])==expected_stages,'Missing/reordered verification stage')
    stages=v['stages']; check(len(stages)>5 and len({s['name'] for s in stages})==len(stages),'Incomplete stages')
    check(all(s['exit_code']==0 and not s['timed_out'] and math.isfinite(s['seconds']) and s['seconds']>=0 for s in stages),'Failed stage')
    for receipt in (v['native_unit'],v['linux_unit']):
        check(receipt['passed'] and receipt['source']==source and receipt['source_sha256']==fingerprint(source),'Wrong unit source')
        check(receipt['tests']==len(receipt['test_ids'])>=37 and len(set(receipt['test_ids']))==receipt['tests'] and
              receipt['errors']==receipt['failures']==receipt['skipped']==0,'Invalid unit receipt')
    check(v['native_unit']['platform']=='Darwin' and v['linux_unit']['platform']=='Linux' and
          v['native_unit']['test_ids']==v['linux_unit']['test_ids'],'Different platform tests')
    g=v['guest']; check(g['passed'] is True and g['source']==source and g['source_sha256']==fingerprint(source),'Guest source')
    expected={name.split('/')[-1]:sha for name,sha in source.items() if name.startswith('fleetweft/')}
    check(g['installed']==expected,'Installed wheel mismatch')
    check(len(g['units'])==4 and all(u['User']=='fleetweft' and u['KillMode']=='control-group' and
          u['NoNewPrivileges']=='yes' and u['CapabilityBoundingSet']=='' and 'fleetweft.mvp serve' in u['ExecStart']
          for u in g['units'].values()),'Shipping service identity')
    rows=g['cases']; check(tuple(r['name'] for r in rows)==CASES and all(r['passed'] is True for r in rows),'Missing scenarios')
    check(all(math.isfinite(r['seconds']) and r['seconds']>=0 for r in rows),'Invalid timing')
    by={r['name']:r for r in rows}; normal=by['three-node-canary']; serving(normal['serving'],'v2')
    check(normal['status']['fleet']['phase']=='COMPLETED','Rollout incomplete')
    events=normal['status']['events']; settled=next(e['sequence'] for e in events if e['kind']=='SETTLED' and e['node']=='a')
    check(all(e['sequence']>settled for e in events if e['kind']=='GRANT' and e['node']!='a'),'Canary bypass')
    failed=by['failed-canary-pauses']; serving(failed['serving'],'v1')
    check(failed['status']['paused'] and failed['status']['fleet']['targets']['a']=='FAILED' and
          not failed['status']['fleet']['canary_passed'],'Failed canary promoted')
    check(not any(e['kind']=='GRANT' and e['node']!='a' for e in failed['status']['events']),'Failed canary follower')
    startup=by['startup-failure-restores']; serving(startup['serving'],'v1')
    check(startup['status']['paused'] and startup['status']['fleet']['targets']['a']=='FAILED','Startup failure promoted')
    rollback=by['later-failure-partial-rollback']; serving(rollback['serving'],'v1')
    check(rollback['partial']['fleet']['phase']!='ROLLED_BACK' and rollback['status']['fleet']['phase']=='ROLLED_BACK','False complete rollback')
    latest=by['offline-latest-catch-up']; serving(latest['serving'],'v3')
    check(latest['status']['history'][0]['phase']=='SUPERSEDED_INCOMPLETE' and
          not any(e['kind']=='GRANT' and e['node']=='c' and e['release']=='v2' for e in latest['status']['events']),'Hidden offline grant')
    held=by['partition-retains-grant']['held']; check(held['paused'] and held['active'] is not None,'Lost unknown occupancy')
    check(by['partition-retains-grant']['status']['active'] is None,'Never reconciled')
    restarted=by['agent-controller-sigkill']; serving(restarted['serving'],'v2')
    check(restarted['old_unit']['InvocationID']!=restarted['new_unit']['InvocationID'] and restarted['restart_seconds']>0,'No actual restart')
    auth=by['mtls-and-tampered-artifact']; check(auth['no_client_certificate_rejected'] and auth['untrusted_ca_rejected'] and len(auth['rejections'])==3 and
          all(r=={'status':409} for r in auth['rejections']),'Auth boundary not tested')
    serving(auth['serving'],'v1'); check(auth['status']['paused'] and auth['status']['fleet']['targets']['a']=='FAILED','Artifact activated')
    delayed=by['delayed-executor-real-backend']; check(delayed['before']['route']==delayed['after']['route'] and delayed['after']['release']=='v3' and delayed['after']['result']==14,'Stale executor changed route')
    measured=by['measured-requests']; req=measured['requests']; check(len(req)==30 and [r['index'] for r in req]==list(range(30)),'Selected/missing requests')
    check(all(r['ok'] and r['release']=='v2' and r['result']==14 and r['seconds']>=0 and math.isfinite(r['seconds']) for r in req),'Failed measured requests')
    check(len(measured['process_rss'])==4 and all(v['rss_kib']>0 for v in measured['process_rss'].values()),'Missing process RSS')
    check(set(measured['worker_rss'])==set('abc') and all(len(v)==1 and v[0]['rss_kib']>0 for v in measured['worker_rss'].values()),'Missing worker RSS')
    from .report import verify_mutations
    verify_mutations(v['mutations'],source)
    before=g['reboot_before']; after=g['reboot_after']; check(before['boot_id']!=after['boot_id'],'VM did not reboot')
    check(after['prestart']['boot_id']==after['boot_id'],'Prestart is from wrong boot')
    original=before['pending']; stored=after['prestart']['states']['a']
    check(original['phase']==stored['phase']=='ACTIVATING' and original['committed']==stored['committed']=='v2' and
          original['token']==stored['accepted'],'Shutdown rollback mistaken for recovery')
    check(after['status']['active'] is None and after['status']['paused'],'Reboot released without reconciliation')
    serving(after['serving'],'v2')
    check(all(before['units'][u]['InvocationID']!=after['units'][u]['InvocationID'] for u in before['units']),'Reused services after reboot')
    check(g['power_loss_tested'] is False and g['boot_zero_gap_tested'] is False,'Untested claim')
    return True

def render(v):
    try: verify(v,v['source']); valid=True
    except Exception: valid=False
    rows=v.get('guest',{}).get('cases',[])
    summary=[dict(name=r['name'],seconds=r['seconds'],passed=r['passed']) for r in rows]
    data=json.dumps(v,indent=2,allow_nan=False)
    return '<!doctype html><meta charset="utf-8"><title>Fleetweft MVP evidence</title><style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere}table{border-collapse:collapse}td,th{padding:.5rem;border:1px solid #aaa}</style><h1>Fleetweft MVP evidence: '+('PASS' if valid else 'INCOMPLETE/FAIL')+'</h1><p>Isolated Linux VM, three network namespaces. This is not a hardware/three-host performance benchmark. Request timing includes new TLS connection setup, HTTP service time and full response read; driver/netns startup is excluded. Thirty sequential requests are a smoke measurement, not saturation throughput. RSS is reported separately for each service process and worker, not VM total memory. Orderly VM restart only. No power-loss or boot-zero-gap claim.</p><pre>'+html.escape(json.dumps(summary,indent=2))+'</pre><details><summary>All evidence and scheduled requests</summary><pre>'+html.escape(data)+'</pre></details>\n'

def controls(v,source):
    changes=[lambda x:x.update(passed=False),lambda x:x.update(source_changed=True),lambda x:x['cleanup'].update(units_stopped=False),
             lambda x:x['guest']['cases'].pop(),lambda x:x['guest']['installed'].clear(),
             lambda x:x['guest'].update(power_loss_tested=True),lambda x:x['guest']['reboot_after'].update(boot_id=x['guest']['reboot_before']['boot_id']),
             lambda x:x['guest']['reboot_after']['prestart']['states']['a'].update(phase='FAILED_RESTORED'),
             lambda x:x['guest']['cases'][0]['serving']['a'].update(result=21),
             lambda x:x['guest']['cases'][1]['status']['fleet'].update(canary_passed=True),
             lambda x:x['guest']['cases'][9]['requests'].pop(),lambda x:x['linux_unit'].update(errors=1),lambda x:x['mutations']['rows'].pop(),
             lambda x:x['guest']['cases'][5]['held'].update(active=None)]
    for mutate in changes:
        bad=copy.deepcopy(v); mutate(bad)
        try: verify(bad,source)
        except (ValueError,KeyError,StopIteration,AssertionError): pass
        else: raise AssertionError('Corrupted report passed')
    return len(changes)


def main():
    import argparse
    from pathlib import Path
    from .evidence import manifest
    p=argparse.ArgumentParser(); p.add_argument('directory'); p.add_argument('--current-source',action='store_true'); a=p.parse_args()
    root=Path(a.directory); value=json.loads((root/'evidence.json').read_text())
    source=manifest() if a.current_source else value['source']
    verify(value,source); count=controls(value,source)
    check((root/'report.html').read_text()==render(value),'HTML differs from validated JSON')
    check(value['controls']==count,'Wrong corruption-control count')
    print(json.dumps(dict(passed=True,run_id=value['run_id'],report_controls=count)))

if __name__=='__main__': main()
