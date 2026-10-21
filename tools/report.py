import copy
import html
import json
import math
import re
from .evidence import fingerprint


def rejection(row):
    assert row=={'exit_code':17,'http_status':409}


def route(row,release):
    assert row['release']==release and isinstance(row['worker'],str) and row['worker']
    assert re.fullmatch('[0-9a-f]{64}',row['digest']) and type(row['port']) is int and 0<row['port']<65536


def external(row,release,challenge='external-probe'):
    route(row['route'],release)
    assert row['release']==release and row['worker']==row['route']['worker']
    assert row['result']==14 and row['challenge']==challenge and row['healthy'] is True
    assert isinstance(row['incarnation'],str) and row['incarnation']


def verify(v, source):
    assert v['passed'] is True and v['source']==source and v['source_sha256']==fingerprint(source)
    assert v['source_changed'] is False and v['vm_initial']=='Stopped' and v['vm_final']=='Stopped'
    assert v['snapshot_removed'] is True and not any(k.endswith('error') for k in v)
    names=['vm-initial','vm-start','preflight','wheel-build','upload','install','guest','remove','vm-stop','vm-final']
    assert [r['name'] for r in v['stages']]==names
    assert all(type(r['exit_code']) is int and r['exit_code']==0 and r['timed_out'] is False for r in v['stages'])
    assert all(type(r['seconds']) in (int,float) and math.isfinite(r['seconds']) and r['seconds']>=0 for r in v['stages'])
    g=v['guest'];assert g['passed'] is True and 'error' not in g and g['source']==source
    assert all(g[k] is True for k in ('cleanup_processes_retired','root_firewall_unchanged','cleanup_namespaces_removed'))
    assert g['scope']=={'isolated_linux_vm':True,'systemd':True,'power_loss_tested':False,'vm_reboot_tested':False,
                        'full_fleet_scheduler_tested':False,'tls_tested':False,'signatures_tested':False}
    assert g['installed']['origin'].startswith('/opt/fleetweft-exploration/venv/lib/')
    assert g['installed']['hashes']=={k:h for k,h in source.items() if k.startswith('fleetweft/')}
    units=g['environment']['units']
    assert set(units)=={'fleetweft-probe-controller.service','fleetweft-probe-node.service'}
    for name,r in units.items():
        assert r['User']=='fleetweft-probe' and r['NoNewPrivileges']=='yes' and r['CapabilityBoundingSet']==''
        assert r['ActiveState']=='active' and r['SubState']=='running' and int(r['MainPID'])>1
        assert r['NetworkNamespacePath']=='/run/netns/'+('fw_ctl' if 'controller' in name else 'fw_node')
        assert r['InvocationID'] and r['ExecMainStatus']=='0'
    u=g['unit_tests'];assert u['passed'] is True and u['source']==source and u['source_sha256']==fingerprint(source)
    assert u['platform']=='Linux' and u['tests']==len(u['test_ids'])==len(set(u['test_ids']))>0
    assert all(u[k]==0 for k in ('errors','failures','skipped'))
    cases=g['cases'];assert [r['name'] for r in cases]==['authorization_loss_partition','delayed_executor','canary_freshness','crash_recovery']
    assert all(r['passed'] is True for r in cases)
    a,e,c,r=[x['evidence'] for x in cases]
    for loss in (a['grant_reply_loss'],a['accept_reply_loss'],r['finish_reply_loss']):
        assert loss['client_failure']=={'exit_code':18,'transport_error':'RemoteDisconnected'}
    assert a['accept_reply_loss']['forwarded_and_reply_dropped']['upstream_result']['token']==a['paused']['active']['token']
    assert a['accept_reply_loss']['forwarded_and_reply_dropped']['upstream_result']['phase']=='STAGED'
    assert a['grant_reply_loss']['forwarded_and_reply_dropped']['upstream_result']==a['paused']['active']['token']
    assert a['paused']['paused'] is True and a['paused']['quiesced'] is False;rejection(a['new_plan_rejected'])
    assert a['partition_client']=={'exit_code':18,'transport_error':'URLError'} and a['cancel_requested']['quiesced'] is False
    assert a['settled']['quiesced'] is True and a['restored']['phase']=='FAILED_RESTORED'
    external(a['local_during_partition'],'v1');external(a['after'],'v1')
    assert e['late_request_exit']==23;rejection(e['stale_ack'])
    rejection(e['staged_rejection']);assert e['staged_before']==e['staged_after']
    assert e['staged_after']['phase']=='STAGED'
    assert e['before']['route']==e['after']['route'] and e['after']['release']=='v3'
    external(e['before'],'v3');external(e['after'],'v3')
    assert [x['mode'] for x in e['worker_retention']]==['commit','cancel','commit','cancel']
    for row in e['worker_retention']:
        assert len(row['before_workers'])==2 and len(row['after']['workers'])==1 and row['obsolete_retired'] is True
        assert row['after']['phase']==('COMMITTED' if row['mode']=='commit' else 'FAILED_RESTORED')
        external(row['external'],row['after']['committed'])
    pin=e['pinned_drain'];assert pin['borrowed_observed'] is True and len(pin['after']['workers'])==1
    external(pin['response'],'v3','pinned');assert pin['response']['route']==pin['candidate']['route']
    assert pin['after']['phase']=='FAILED_RESTORED';external(pin['external_after'],pin['after']['committed'])
    assert c['wrong_business_result']['result']==21
    for k in ('wrong_data_rejected','insufficient_rejected','premature_commit_rejected','replay_rejected','expired_rejected','old_incarnation_rejected'):
        rejection(c[k])
    assert c['reset_observation']['active']['evidence'] is None and c['reset_observation']['active']['binding'] is None
    assert [p['sequence'] for p in c['fresh_samples']]==[1,2,3]
    assert all(p['result']==p['input']*2 for p in c['fresh_samples'])
    observation=c['observed']['active'];ev=observation['evidence'];assert ev['count']==3 and ev['sequence']==3
    assert 0<ev['started_ns']<=ev['finished_ns'] and (ev['finished_ns']-ev['started_ns'])/1e9>=.05
    assert len({p['challenge'] for p in c['fresh_samples']})==3
    for p in c['fresh_samples']:
        assert p['route']==observation['binding'] and p['token']==observation['token']
        assert p['incarnation']==c['observed']['agents']['a'] and p['phase']=='OBSERVING'
    assert c['committed']['phase']=='COMMITTED';external(c['external'],'v2')
    assert [x['point'] for x in r['node_boundaries']]==['staged','before_route','after_route','before_commit','after_commit']
    for row in r['node_boundaries']:
        committed=row['point']=='after_commit';release='v2' if committed else 'v1'
        assert row['unit_failed']['Result']=='signal' and row['unit_failed']['ExecMainStatus']=='9'
        assert row['unit_before']['InvocationID']==row['unit_failed']['InvocationID']
        assert row['unit_before']['ActiveState']=='active' and int(row['unit_before']['MainPID'])>1
        assert row['unit_failed']['ActiveState']=='failed' and row['unit_failed']['MainPID']=='0'
        assert row['children_retired'] is True
        assert row['before_committed']==release
        expected_phase={'staged':'STAGED','before_route':'ACTIVATING','after_route':'ACTIVATING','before_commit':'OBSERVING','after_commit':'COMMITTED'}[row['point']]
        assert row['before_phase']==expected_phase
        external(row['actual_before'],'v2' if row['point'] in ('after_route','before_commit','after_commit') else 'v1')
        assert row['external_after']['release']==row['after']['committed']==release
        assert row['after']['phase']==('COMMITTED' if committed else 'FAILED_RESTORED')
        external(row['external_after'],release)
        assert row['settled']['quiesced'] is True and row['settled']['paused'] is True
    assert r['finish_retry']['quiesced'] is True
    assert r['controller_after']['epoch']>r['controller_before']['epoch']
    assert r['controller_after']['active']['token']==r['controller_before']['active']['token']
    assert r['controller_after']['active']['needs_reconcile'] is True and r['controller_after']['quiesced'] is False
    assert r['controller_after']['active']['binding'] is None and r['controller_after']['active']['evidence'] is None
    rejection(r['new_plan_rejected']);assert r['settled']['quiesced'] is True
    external(r['external'],'v2')


def verify_native(n,source,ids):
    assert n['passed'] is True and n['platform']=='Darwin' and n['source']==source
    assert n['source_sha256']==fingerprint(source) and n['test_ids']==ids
    assert n['tests']==len(ids)>0 and all(n[k]==0 for k in ('errors','failures','skipped'))


def verify_mutations(m,source):
    from .mutations import MUTATIONS
    assert m['passed'] is True and m['source']==source
    assert [(r['name'],r['test']) for r in m['rows']]==[(name,test) for _,name,_,_,test in MUTATIONS]
    assert len({r['name'] for r in m['rows']})==len(MUTATIONS)
    assert all(r['caught_by_assertion'] is True and r['exit_code']==1 for r in m['rows'])


def controls(v, source):
    def case(x,i):return x['guest']['cases'][i]['evidence']
    changes=[('timeout',lambda x:x['stages'][0].update(timed_out=True)),
             ('source',lambda x:x.update(source_sha256='0'*64)),
             ('missing-case',lambda x:x['guest']['cases'].pop()),
             ('free-unknown-slot',lambda x:case(x,0)['paused'].update(quiesced=True)),
             ('accept-new-during-partition',lambda x:case(x,0)['new_plan_rejected'].update(exit_code=0)),
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
    changes += [('missing-units',lambda x:x['guest']['environment'].update(units={})),
                ('wrong-partition-failure',lambda x:case(x,0)['partition_client'].update(exit_code=255)),
                ('execution-error-is-not-rejection',lambda x:case(x,0)['new_plan_rejected'].update(exit_code=-9)),
                ('restore-wrong-data',lambda x:case(x,0)['after'].update(result=21)),
                ('before-route-wrong-data',lambda x:case(x,3)['node_boundaries'][1]['actual_before'].update(result=21)),
                ('after-route-not-activated',lambda x:case(x,3)['node_boundaries'][2]['actual_before'].update(release='v1')),
                ('wrong-pre-crash-phase',lambda x:case(x,3)['node_boundaries'][3].update(before_phase='COMMITTED')),
                ('leaked-workers',lambda x:case(x,1)['worker_retention'][0]['after']['workers'].append({'pid':1})),
                ('pinned-request-wrong-worker',lambda x:case(x,1)['pinned_drain']['response'].update(worker='wrong')),
                ('canary-window-too-short',lambda x:case(x,2)['observed']['active']['evidence'].update(finished_ns=case(x,2)['observed']['active']['evidence']['started_ns'])),
                ('unbounded-stage-time',lambda x:x['stages'][0].update(seconds=float('inf')))]
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
    if (root/'native-unit.json').exists():
        verify_native(json.loads((root/'native-unit.json').read_text()),v['source'],v['guest']['unit_tests']['test_ids'])
    if (root/'mutations.json').exists():
        verify_mutations(json.loads((root/'mutations.json').read_text()),v['source'])
    print('PASS: provenance, actual service observations, scope, controls and exact HTML')
