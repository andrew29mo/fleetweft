"""Root test fixture only. Actual services run unprivileged in separate netns."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import urllib.error

if __package__ in (None, ''): sys.path.append(str(Path(__file__).resolve().parents[1]))
from fleetweft.net import request
from fleetweft.node import recipe_digest, identity
from tools.evidence import manifest

ROOT = Path('/opt/fleetweft-exploration')
STATE = Path('/var/lib/fleetweft-exploration')
PY = str(ROOT / 'venv/bin/python')
CTL, NODE = 'http://10.91.0.1:19081', 'http://10.91.0.2:19082'
CU, NU = 'fleetweft-probe-controller.service', 'fleetweft-probe-node.service'
ALL_CASES = []


def cmd(args, check=True, timeout=15, **kw):
    p = subprocess.run([str(x) for x in args], capture_output=True, text=True, timeout=timeout, **kw)
    if check and p.returncode: raise RuntimeError(str(args[:3]) + ': ' + (p.stdout+p.stderr)[-2000:])
    return p


def wait(fn, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            v = fn()
            if v: return v
        except (OSError, ValueError, RuntimeError): pass
        time.sleep(.025)
    raise AssertionError('Observation timeout')


def props(unit):
    keys = ['MainPID', 'ActiveState', 'SubState', 'Result', 'ExecMainStatus', 'InvocationID',
            'User', 'NoNewPrivileges', 'CapabilityBoundingSet', 'NetworkNamespacePath']
    return dict(r.split('=', 1) for r in cmd(['systemctl', 'show', unit, *['-p'+k for k in keys]]).stdout.splitlines())


def root_digest():
    return hashlib.sha256(cmd(['nft', '-j', '-s', 'list', 'ruleset']).stdout.encode()).hexdigest()


def ncall(url, path, body=None, fail=False):
    # Run the real client inside the agent namespace: partition tests cannot
    # accidentally bypass the broken link through a root-namespace connection.
    script = '''import json,sys,urllib.error
from fleetweft.net import request
try:print(json.dumps(request(sys.argv[1],sys.argv[2],json.loads(sys.argv[3]))))
except urllib.error.HTTPError as e:
 print(json.dumps({'http_status':e.code}));sys.exit(17)
except (urllib.error.URLError,OSError) as e:
 print(json.dumps({'transport_error':type(e).__name__}));sys.exit(18)
'''
    p = cmd(['ip', 'netns', 'exec', 'fw_node', PY, '-I', '-c', script, url, path, json.dumps(body)], check=not fail, timeout=5)
    if fail:
        value=json.loads(p.stdout)
        if fail=='transport':assert p.returncode==18 and 'transport_error' in value
        else:assert p.returncode==17 and value['http_status']==409
        return {'exit_code': p.returncode,**value}
    return json.loads(p.stdout)


def c(path, body=None, **kw): return ncall(CTL, path, body, **kw)
def n(path, body=None, **kw): return ncall(NODE, path, body, **kw)


def reset():
    for u in (NU, CU): cmd(['systemctl', 'stop', u], check=False)
    for name in ('node', 'controller'):
        shutil.rmtree(STATE / name, ignore_errors=True)
        (STATE / name).mkdir(mode=0o700)
        shutil.chown(STATE / name, user='fleetweft-probe', group='fleetweft-probe')
    drop = Path('/etc/systemd/system/' + NU + '.d')
    if drop.exists(): shutil.rmtree(drop)
    cmd(['systemctl', 'daemon-reload']); cmd(['systemctl', 'reset-failed', NU, CU], check=False)
    cmd(['systemctl', 'start', CU, NU])
    try:wait(lambda: n('/status'))
    except AssertionError:
        raise RuntimeError('Node readiness timeout: '+str(props(NU))+' '+cmd(['journalctl','-u',NU,'--no-pager','-n','20']).stdout)
    s = n('/status'); c('/register', {'node': 'a', 'incarnation': s['incarnation'], 'expected': None})
    return s


def plan(release='v2'):
    s = n('/status'); c('/plan', {'node': 'a', 'release': release, 'baseline': s['committed']})
    t = c('/grant', {'node': 'a'})
    a = n('/accept', {'token': t, 'incarnation': s['incarnation']})
    return a


def start_candidate(status):
    a = n('/activate', status); c('/bind', a); return a


def observe():
    receipts = []
    for seq in (1, 2, 3):
        s = n('/status'); a = c('/status')['active']
        p = n('/sample', {**s, 'input': 7, 'sequence': seq, 'challenge': a['challenge']})
        receipts.append(p); c('/sample', p); time.sleep(.06)
    return receipts


def finish():
    s = n('/status'); committed = n('/commit', s); result = c('/finish', committed)
    assert result['quiesced']; return committed


def work(release):
    v = n('/work?x=7&challenge=external-probe')
    assert v['release'] == release and v['result'] == 14 and v['challenge'] == 'external-probe'
    assert v['route']['digest'] == recipe_digest(release)
    return v


def record(name, evidence):
    ALL_CASES.append({'name': name, 'passed': True, 'evidence': evidence})


def proxy():
    upstream, trace = sys.argv[2], Path(sys.argv[3])
    class DropReply(BaseHTTPRequestHandler):
        def do_POST(self):
            p = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            result = request(upstream, self.path, p)
            trace.write_text(json.dumps({'path': self.path, 'upstream_result': result}))
            self.connection.shutdown(2); self.connection.close()
        def log_message(self, *args): pass
    ThreadingHTTPServer(('127.0.0.1', 19083), DropReply).serve_forever()


def lose_reply(upstream, path, payload):
    trace = STATE / 'reply-loss.json'; trace.unlink(missing_ok=True)
    p = subprocess.Popen(['ip', 'netns', 'exec', 'fw_node', PY, '-I', str(ROOT/'source/tools/guest.py'),
                          'proxy', upstream, str(trace)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait(lambda: cmd(['ip', 'netns', 'exec', 'fw_node', 'ss', '-lntH']).stdout.find(':19083') >= 0)
        rejected = ncall('http://127.0.0.1:19083', path, payload, fail='transport')
        receipt = json.loads(trace.read_text()); assert receipt['path'] == path
        return {'client_failure': rejected, 'forwarded_and_reply_dropped': receipt}
    finally:
        p.kill(); p.wait(timeout=3)


def authorization():
    reset(); c('/plan', {'node': 'a', 'release': 'v2', 'baseline': 'v1'})
    loss = lose_reply(CTL, '/grant', {'node': 'a'}); before = c('/status')
    t = c('/grant', {'node': 'a'}); assert t == loss['forwarded_and_reply_dropped']['upstream_result']
    s = n('/status'); accept_loss = lose_reply(NODE, '/accept', {'token': t, 'incarnation': s['incarnation']})
    accepted = n('/accept', {'token': t, 'incarnation': s['incarnation']})
    assert accepted == accept_loss['forwarded_and_reply_dropped']['upstream_result']
    cmd(['ip', '-n', 'fw_ctl', 'link', 'set', 'fc0', 'down'])
    partition = c('/status', fail='transport'); local_during = work('v1')
    # Controller is directly inspected in its own namespace during real partition.
    direct = json.loads(cmd(['ip', 'netns', 'exec', 'fw_ctl', PY, '-I', '-c',
        "import json;from fleetweft.net import request;print(json.dumps(request('http://127.0.0.1:19081','/pause',{})))"]).stdout)
    assert direct['paused'] and not direct['quiesced'] and direct['active']['token'] == t
    blocked = cmd(['ip', 'netns', 'exec', 'fw_ctl', PY, '-I', '-c',
        "from fleetweft.net import request;request('http://127.0.0.1:19081','/plan',{'node':'a','release':'v3','baseline':'v1'})"], check=False)
    assert blocked.returncode != 0
    cmd(['ip', '-n', 'fw_ctl', 'link', 'set', 'fc0', 'up'])
    cancel = c('/cancel', {}); assert not cancel['quiesced']
    restored = n('/cancel', accepted); settled = c('/finish', restored)
    assert settled['quiesced'] and settled['last']['phase'] == 'FAILED_RESTORED'
    record('authorization_loss_partition', {'grant_reply_loss': loss, 'accept_reply_loss': accept_loss,
        'before': before, 'partition_client': partition, 'local_during_partition': local_during,
        'paused': direct, 'new_plan_rejected': blocked.returncode, 'cancel_requested': cancel,
        'restored': restored, 'settled': settled, 'after': work('v1')})


def stale_executor():
    reset(); old = plan(); start_candidate(old); observe(); finish()
    # An external executor has already passed a preflight read, then stops
    # before the actual switch request. It has no direct route write handle.
    preflight = n('/status'); reached = STATE/'executor-ready'; release = STATE/'executor-go'
    reached.unlink(missing_ok=True); release.unlink(missing_ok=True)
    script = '''import json,sys,time
from pathlib import Path
from fleetweft.net import request
p=json.loads(sys.argv[1]);Path(sys.argv[2]).write_text('ready')
while not Path(sys.argv[3]).exists():time.sleep(.01)
try:request(sys.argv[4],'/activate',p)
except Exception as e:
 import urllib.error
 if isinstance(e,urllib.error.HTTPError) and e.code==409:sys.exit(23)
 raise
sys.exit(0)
'''
    p = subprocess.Popen(['ip','netns','exec','fw_node',PY,'-I','-c',script,json.dumps(preflight),str(reached),str(release),NODE])
    try:
        wait(reached.exists); os.kill(p.pid, signal.SIGSTOP)
        successor = plan('v3');staged_before=n('/status')
        staged_rejection=n('/activate',preflight,fail=True);staged_after=n('/status')
        assert staged_before==staged_after and staged_after['phase']=='STAGED'
        start_candidate(successor); observe(); finish(); before = work('v3')
        release.touch(); os.kill(p.pid, signal.SIGCONT); p.wait(timeout=4)
        assert p.returncode == 23; stale_ack = c('/finish', preflight, fail=True); after = work('v3')
        assert before['route'] == after['route']
        record('delayed_executor', {'preflight': preflight, 'successor': successor, 'late_request_exit': p.returncode,
            'staged_rejection':staged_rejection,'staged_before':staged_before,'staged_after':staged_after,
            'stale_ack': stale_ack, 'before': before, 'after': after,
            'boundary': 'Cached preflight before resource request; unique writer rechecks at mutation, not paused inside its critical section'})
    finally:
        if p.poll() is None: os.kill(p.pid,signal.SIGCONT);p.kill();p.wait()


def canary():
    reset(); a = plan('bad'); start_candidate(a)
    status=n('/status'); active=c('/status')['active']
    sample=n('/sample',{**status,'input':7,'sequence':1,'challenge':active['challenge']})
    assert sample['result']==21
    bad=c('/sample',sample,fail=True); insufficient=c('/finish',{**status,'phase':'COMMITTED'},fail=True)
    premature=n('/commit',status,fail=True)
    assert n('/status')['committed']=='v1'
    restored=n('/cancel',status);c('/finish',restored);c('/resume',{})
    a=plan();start_candidate(a); s=n('/status');active=c('/status')['active']
    old=n('/sample',{**s,'input':7,'sequence':1,'challenge':active['challenge']})
    c('/sample',old); replay=c('/sample',old,fail=True)
    stale={**old,'challenge':c('/status')['active']['challenge'],'sequence':2}
    time.sleep(2.1);expired=c('/sample',stale,fail=True)
    cmd(['systemctl','kill','--kill-whom=main','--signal=SIGKILL',NU]);wait(lambda:props(NU)['ActiveState']=='failed')
    cmd(['systemctl','reset-failed',NU]);cmd(['systemctl','start',NU]);current=wait(lambda:n('/status'))
    assert current['incarnation']!=s['incarnation'] and current['phase']=='FAILED_RESTORED'
    c('/register',{'node':'a','incarnation':current['incarnation'],'expected':s['incarnation']})
    old_after_restart=c('/sample',stale,fail=True);state=c('/status')
    assert state['active']['binding'] is None and state['active']['evidence'] is None
    c('/reconcile',current);c('/resume',{});a=plan();start_candidate(a);fresh=observe();committed=finish()
    record('canary_freshness',{'wrong_business_result':sample,'wrong_data_rejected':bad,'insufficient_rejected':insufficient,
        'premature_commit_rejected':premature,
        'replay_rejected':replay,'expired_rejected':expired,'old_incarnation_rejected':old_after_restart,
        'reset_observation':state,'fresh_samples':fresh,'committed':committed,'external':work('v2')})


def crashes():
    rows=[]
    for point in ('staged','before_route','after_route','before_commit','after_commit'):
        reset();a=plan()
        cmd(['systemctl','stop',NU]);checkpoint=STATE/'node/checkpoint';go=STATE/'node/release-checkpoint'
        checkpoint.unlink(missing_ok=True);go.unlink(missing_ok=True)
        drop=Path('/etc/systemd/system/'+NU+'.d');drop.mkdir(exist_ok=True)
        (drop/'barrier.conf').write_text('[Service]\nEnvironment=FLEETWEFT_CHECKPOINT='+point+'\n')
        # A normal restart of STAGED intentionally compensates. Start a fresh
        # operation after this, rather than secretly repairing its journal.
        cmd(['systemctl','daemon-reload']);cmd(['systemctl','start',NU]);s=wait(lambda:n('/status'))
        c('/register',{'node':'a','incarnation':s['incarnation'],'expected':a['incarnation']})
        c('/reconcile',s);c('/resume',{})
        c('/plan',{'node':'a','release':'v2','baseline':'v1'});t=c('/grant',{'node':'a'})
        payload={'token':t,'incarnation':s['incarnation']}
        action='accept' if point=='staged' else 'activate'
        if point!='staged':a=n('/accept',payload)
        if point in ('before_commit','after_commit'):
            start_candidate(a);observe();action='commit'
        script='import json,sys;from fleetweft.net import request;request(sys.argv[1],sys.argv[2],json.loads(sys.argv[3]))'
        client=subprocess.Popen(['ip','netns','exec','fw_node',PY,'-I','-c',script,NODE,'/'+action,json.dumps(payload)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            wait(checkpoint.exists);unit_before=props(NU)
            # Gateway reads do not take the mutation lock: observe actual route
            # even while the mutation handler is stopped at a test barrier.
            seen=work('v2' if point in ('after_route','before_commit','after_commit') else 'v1')
            import sqlite3
            with sqlite3.connect(STATE/'node/state.sqlite') as db:before=json.loads(db.execute('SELECT data FROM snapshot').fetchone()[0])
            children=before['children']
            cmd(['systemctl','kill','--kill-whom=main','--signal=SIGKILL',NU]);wait(lambda:props(NU)['ActiveState']=='failed')
            client.wait(timeout=3);assert client.returncode!=0
            assert all(identity(i['pid'])!=i for i in children)
            unit_failed=props(NU);assert unit_failed['Result']=='signal' and unit_failed['ExecMainStatus']=='9'
            shutil.rmtree(drop);cmd(['systemctl','daemon-reload']);cmd(['systemctl','reset-failed',NU]);cmd(['systemctl','start',NU])
            after=wait(lambda:n('/status'));target='v2' if point=='after_commit' else 'v1'
            assert after['committed']==target and after['phase']==('COMMITTED' if point=='after_commit' else 'FAILED_RESTORED')
            c('/register',{'node':'a','incarnation':after['incarnation'],'expected':s['incarnation']})
            settled=c('/reconcile',after);assert settled['quiesced'] and settled['paused']
            rows.append({'point':point,'before_phase':before['phase'],'before_committed':before['committed'],
                'actual_before':seen,'unit_before':unit_before,'unit_failed':unit_failed,'children_retired':True,
                'after':after,'settled':settled,'external_after':work(target)})
        finally:
            if client.poll() is None:client.kill();client.wait()
    # A Controller crash retains occupancy and invalidates health observations.
    reset();a=plan();start_candidate(a);observe();committed=n('/commit',n('/status'))
    lost=lose_reply(CTL,'/finish',committed)
    retry=c('/finish',committed);assert retry['quiesced']
    a=plan('v3');before=c('/status')
    cmd(['systemctl','kill','--kill-whom=main','--signal=SIGKILL',CU]);wait(lambda:props(CU)['ActiveState']=='failed')
    cmd(['systemctl','reset-failed',CU]);cmd(['systemctl','start',CU]);after=wait(lambda:c('/status'))
    assert after['epoch']>before['epoch'] and after['active']['token']==before['active']['token']
    assert after['active']['needs_reconcile'] and not after['quiesced']
    denied=c('/plan',{'node':'a','release':'v1','baseline':'v2'},fail=True)
    restored=n('/cancel',a);settled=c('/reconcile',restored)
    record('crash_recovery',{'node_boundaries':rows,'finish_reply_loss':lost,'finish_retry':retry,
        'controller_before':before,'controller_after':after,'new_plan_rejected':denied,'settled':settled,'external':work('v2')})


def cleanup():
    assert (STATE/'fixture-owner').read_text()=='fleetweft-exploration-v1'
    for unit in (NU,CU):cmd(['systemctl','stop',unit],check=False)
    retired=all(props(u)['MainPID']=='0' for u in (NU,CU))
    assert retired
    for unit in (NU,CU):
        Path('/etc/systemd/system/'+unit).unlink(missing_ok=True)
        shutil.rmtree('/etc/systemd/system/'+unit+'.d',ignore_errors=True)
    cmd(['systemctl','daemon-reload']);cmd(['systemctl','reset-failed',NU,CU],check=False)
    for ns in ('fw_node','fw_ctl'):cmd(['ip','netns','del',ns],check=False)
    cmd(['userdel','fleetweft-probe'],check=False);shutil.rmtree(STATE)
    return {'processes_retired':retired}


def main():
    value={'passed':False,'source':manifest(ROOT/'source'),'cases':ALL_CASES,
           'scope':{'isolated_linux_vm':True,'systemd':True,'power_loss_tested':False,'vm_reboot_tested':False,
                    'full_fleet_scheduler_tested':False,'tls_tested':False,'signatures_tested':False}}
    initial=root_digest();setup=False
    try:
        assert not STATE.exists() and cmd(['id','fleetweft-probe'],check=False).returncode!=0
        assert all(ns not in cmd(['ip','netns','list']).stdout for ns in ('fw_node','fw_ctl'))
        assert all(not Path('/etc/systemd/system/'+u).exists() for u in (NU,CU))
        STATE.mkdir(mode=0o755);(STATE/'fixture-owner').write_text('fleetweft-exploration-v1');setup=True
        cmd(['useradd','--system','--no-create-home','--shell','/usr/sbin/nologin','fleetweft-probe'])
        for ns in ('fw_ctl','fw_node'):
            cmd(['ip','netns','add',ns]);cmd(['ip','-n',ns,'link','set','lo','up'])
        cmd(['ip','-n','fw_ctl','link','add','fc0','type','veth','peer','name','fn0','netns','fw_node'])
        for ns,dev,ip in [('fw_ctl','fc0','10.91.0.1/24'),('fw_node','fn0','10.91.0.2/24')]:
            cmd(['ip','-n',ns,'addr','add',ip,'dev',dev]);cmd(['ip','-n',ns,'link','set',dev,'up'])
        for role,unit,ns,port,bind in [('controller',CU,'fw_ctl',19081,'0.0.0.0'),('node',NU,'fw_node',19082,'0.0.0.0')]:
            text='[Unit]\nDescription=Fleetweft isolated exploration '+role+'\n[Service]\nType=simple\nUser=fleetweft-probe\nNetworkNamespacePath=/run/netns/'+ns+'\nExecStart='+PY+' -I -m fleetweft.service '+role+' --state '+str(STATE/role)+' --listen '+bind+' --port '+str(port)+' --controller '+CTL+'\nKillMode=control-group\nTimeoutStopSec=5\nNoNewPrivileges=yes\nCapabilityBoundingSet=\nProtectSystem=strict\nProtectHome=yes\nPrivateTmp=yes\nReadWritePaths='+str(STATE)+'\nUMask=0077\n'
            Path('/etc/systemd/system/'+unit).write_text(text)
        cmd(['systemctl','daemon-reload']);reset()
        import fleetweft
        installed=Path(fleetweft.__file__).parent
        hashes={str(p.relative_to(installed.parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in installed.glob('*.py')}
        assert hashes=={k:v for k,v in value['source'].items() if k.startswith('fleetweft/')}
        value['installed']={'origin':str(installed),'hashes':hashes}
        value['environment']={'kernel':cmd(['uname','-r']).stdout.strip(),'systemd':cmd(['systemctl','--version']).stdout.splitlines()[0],
                              'python':sys.version.split()[0],'architecture':cmd(['uname','-m']).stdout.strip(),
                              'units':{CU:props(CU),NU:props(NU)}}
        cmd([PY,'-m','tools.unit','--output',str(STATE/'unit.json')],cwd=ROOT/'source',timeout=60)
        value['unit_tests']=json.loads((STATE/'unit.json').read_text())
        authorization();stale_executor();canary();crashes()
        value['passed']=True
    except BaseException as exc:
        import traceback
        value['error']=type(exc).__name__+': '+str(exc)
        traceback.print_exc(file=sys.stderr)
    finally:
        if setup:
            value['cleanup_processes_retired']=cleanup()['processes_retired']
        value['root_firewall_unchanged']=root_digest()==initial
        value['cleanup_namespaces_removed']=all(ns not in cmd(['ip','netns','list']).stdout for ns in ('fw_node','fw_ctl'))
        value['passed']=value['passed'] and value.get('cleanup_processes_retired',False) and value['root_firewall_unchanged'] and value['cleanup_namespaces_removed']
    print(json.dumps(value));raise SystemExit(0 if value['passed'] else 1)


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='proxy':proxy()
    elif len(sys.argv)>1 and sys.argv[1]=='cleanup':print(json.dumps(cleanup()))
    else:main()
