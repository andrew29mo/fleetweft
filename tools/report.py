import copy
import html
import json
from .evidence import fingerprint


def verify(v, source):
    assert v['passed'] is True and v['source']==source and v['source_sha256']==fingerprint(source)
    assert v['source_changed'] is False and v['vm_initial']=='Stopped' and v['vm_final']=='Stopped'
    assert v['snapshot_removed'] is True and not any(k.endswith('error') for k in v)
    names=['vm-initial','vm-start','preflight','wheel-build','upload','install','guest','remove','vm-stop','vm-final']
    assert [r['name'] for r in v['stages']]==names
    assert all(type(r['exit_code']) is int and r['exit_code']==0 and r['timed_out'] is False for r in v['stages'])
    g=v['guest'];assert g['passed'] is True and 'error' not in g and g['source']==source
    assert all(g[k] is True for k in ('cleanup_processes_retired','root_firewall_unchanged','cleanup_namespaces_removed'))
    assert g['scope']=={'isolated_linux_vm':True,'systemd':True,'power_loss_tested':False,'vm_reboot_tested':False,
                        'full_fleet_scheduler_tested':False,'tls_tested':False,'signatures_tested':False}
    assert g['installed']['origin'].startswith('/opt/fleetweft-exploration/venv/lib/')
    assert g['installed']['hashes']=={k:h for k,h in source.items() if k.startswith('fleetweft/')}
    for r in g['environment']['units'].values():
        assert r['User']=='fleetweft-probe' and r['NoNewPrivileges']=='yes' and r['CapabilityBoundingSet']==''
        assert r['ActiveState']=='active' and r['SubState']=='running' and int(r['MainPID'])>1
    u=g['unit_tests'];assert u['passed'] is True and u['source']==source and u['source_sha256']==fingerprint(source)
    assert u['platform']=='Linux' and u['tests']==len(u['test_ids'])==len(set(u['test_ids']))>0
    assert all(u[k]==0 for k in ('errors','failures','skipped'))
    cases=g['cases'];assert [r['name'] for r in cases]==['authorization_loss_partition','delayed_executor','canary_freshness','crash_recovery']
    assert all(r['passed'] is True for r in cases)
    a,e,c,r=[x['evidence'] for x in cases]
    for loss in (a['grant_reply_loss'],a['accept_reply_loss'],r['finish_reply_loss']):assert loss['client_failure']['exit_code']!=0
    assert a['grant_reply_loss']['forwarded_and_reply_dropped']['upstream_result']==a['paused']['active']['token']
    assert a['paused']['paused'] is True and a['paused']['quiesced'] is False and a['new_plan_rejected']!=0
    assert a['partition_client']['exit_code']!=0 and a['cancel_requested']['quiesced'] is False
    assert a['settled']['quiesced'] is True and a['restored']['phase']=='FAILED_RESTORED'
    assert a['local_during_partition']['release']==a['after']['release']=='v1'
    assert e['late_request_exit']==23 and e['stale_ack']['exit_code']!=0
    assert e['staged_rejection']['http_status']==409 and e['staged_before']==e['staged_after']
    assert e['staged_after']['phase']=='STAGED'
    assert e['before']['route']==e['after']['route'] and e['after']['release']=='v3'
    assert c['wrong_business_result']['result']==21
    for k in ('wrong_data_rejected','insufficient_rejected','premature_commit_rejected','replay_rejected','expired_rejected','old_incarnation_rejected'):
        assert c[k]['exit_code']==17 and c[k]['http_status']==409
    assert c['reset_observation']['active']['evidence'] is None and c['reset_observation']['active']['binding'] is None
    assert [p['sequence'] for p in c['fresh_samples']]==[1,2,3]
    assert all(p['result']==p['input']*2 for p in c['fresh_samples'])
    assert c['committed']['phase']=='COMMITTED' and c['external']['release']=='v2'
    assert [x['point'] for x in r['node_boundaries']]==['staged','before_route','after_route','before_commit','after_commit']
    for row in r['node_boundaries']:
        committed=row['point']=='after_commit';release='v2' if committed else 'v1'
        assert row['unit_failed']['Result']=='signal' and row['unit_failed']['ExecMainStatus']=='9'
        assert row['unit_before']['InvocationID']==row['unit_failed']['InvocationID']
        assert row['children_retired'] is True
        assert row['before_committed']==release
        assert row['external_after']['release']==row['after']['committed']==release
        assert row['after']['phase']==('COMMITTED' if committed else 'FAILED_RESTORED')
        assert row['settled']['quiesced'] is True and row['settled']['paused'] is True
    assert r['finish_retry']['quiesced'] is True
    assert r['controller_after']['epoch']>r['controller_before']['epoch']
    assert r['controller_after']['active']['token']==r['controller_before']['active']['token']
    assert r['controller_after']['active']['needs_reconcile'] is True and r['controller_after']['quiesced'] is False
    assert r['new_plan_rejected']['exit_code']!=0 and r['settled']['quiesced'] is True


def controls(v, source):
    def case(x,i):return x['guest']['cases'][i]['evidence']
    changes=[('timeout',lambda x:x['stages'][0].update(timed_out=True)),
             ('source',lambda x:x.update(source_sha256='0'*64)),
             ('missing-case',lambda x:x['guest']['cases'].pop()),
             ('free-unknown-slot',lambda x:case(x,0)['paused'].update(quiesced=True)),
             ('accept-new-during-partition',lambda x:case(x,0).update(new_plan_rejected=0)),
             ('old-switch-accepted',lambda x:case(x,1).update(late_request_exit=0)),
             ('old-valid-phase-switch',lambda x:case(x,1)['staged_rejection'].update(http_status=200)),
             ('old-switch-changed-route',lambda x:case(x,1)['after'].update(release='v2')),
             ('bad-canary-accepted',lambda x:case(x,2)['wrong_data_rejected'].update(exit_code=0)),
             ('commit-gate-bypassed',lambda x:case(x,2)['premature_commit_rejected'].update(exit_code=0)),
             ('old-canary-accepted',lambda x:case(x,2)['old_incarnation_rejected'].update(exit_code=0)),
             ('uncommitted-recovery-wrong',lambda x:case(x,3)['node_boundaries'][2]['after'].update(committed='v2')),
             ('committed-recovery-wrong',lambda x:case(x,3)['node_boundaries'][4]['after'].update(committed='v1')),
             ('stale-epoch',lambda x:case(x,3)['controller_after'].update(epoch=0)),
             ('cleanup',lambda x:x.update(snapshot_removed=False)),
             ('power-loss-claim',lambda x:x['guest']['scope'].update(power_loss_tested=True))]
    result=[]
    for name,mutate in changes:
        broken=copy.deepcopy(v);mutate(broken)
        try:verify(broken,source)
        except (AssertionError,KeyError,TypeError,ValueError):result.append({'name':name,'rejected':True})
        else:raise AssertionError('Accepted broken evidence '+name)
    return result


def render(v):
    good=False
    try:
        verify(v,v['source']);assert v['controls']==controls(v,v['source'])
    except (AssertionError,KeyError,TypeError,ValueError):pass
    else:good=True
    return '<!doctype html><meta charset="utf-8"><title>Fleetweft explorations</title><style>body{font:16px system-ui;max-width:1000px;margin:40px auto;padding:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>'+('PASS' if good else 'FAIL / INCOMPLETE')+'</h1><p>Isolated Linux VM, unprivileged installed services. Protocol explorations only; no complete fleet scheduler, TLS/signature, VM reboot or sudden power-loss claim.</p><pre>'+html.escape(json.dumps(v,indent=2,allow_nan=False))+'</pre>\n'


if __name__=='__main__':
    import argparse
    from pathlib import Path
    from .evidence import manifest
    p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('--current-source',action='store_true');a=p.parse_args()
    root=Path(a.directory);v=json.loads((root/'evidence.json').read_text());verify(v,manifest() if a.current_source else v['source'])
    assert v['controls']==controls(v,v['source']) and (root/'report.html').read_text()==render(v)
    print('PASS: provenance, actual service observations, scope, controls and exact HTML')
