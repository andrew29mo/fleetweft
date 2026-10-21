"""Isolated VM fixture. Executes the installed wheel and shipping systemd units."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

SOURCE=Path(__file__).resolve().parents[1]
if str(SOURCE) not in sys.path: sys.path.append(str(SOURCE))
from fleetweft.artifacts import Artifacts
from fleetweft.mvp import provision
from fleetweft.coordinator import Coordinator
from fleetweft.store import Store
from fleetweft.node import Node
from tools.mvp_fixture import credentials,bundles
from tools.evidence import manifest,fingerprint
from tools.mvp_ownership import Ownership,preflight

ROOT=Path('/opt/fleetweft'); STATE=Path('/var/lib/fleetweft'); CONF=Path('/etc/fleetweft')
KEYS=Path('/root/fleetweft-fixture'); PY=str(ROOT/'venv/bin/python')
UNITS=['fleetweft-controller.service']+['fleetweft-node@'+n+'.service' for n in 'abc']
PORT=19443; IPS={'controller':'192.0.2.1','a':'192.0.2.11','b':'192.0.2.12','c':'192.0.2.13','operator':'192.0.2.1'}
CASES=[]

def run(args,check=True,timeout=20,**kwargs):
    p=subprocess.run([str(a) for a in args],capture_output=True,text=True,timeout=timeout,**kwargs)
    if check and p.returncode: raise RuntimeError(str(args[:3])+': '+(p.stdout+p.stderr)[-2500:])
    return p

def wait(fn,timeout=20):
    end=time.monotonic()+timeout; last=None
    while time.monotonic()<end:
        try:
            value=fn()
            if value: return value
        except (ValueError,OSError,RuntimeError) as e: last=type(e).__name__
        time.sleep(.05)
    raise AssertionError('Observation timeout '+str(last))

def bootid(): return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
def props(unit):
    keys=['MainPID','InvocationID','ActiveState','User','KillMode','ExecStart','NetworkNamespacePath','NoNewPrivileges','CapabilityBoundingSet']
    return dict(x.split('=',1) for x in run(['systemctl','show',unit,*['-p'+k for k in keys]]).stdout.splitlines())
def firewall(): return hashlib.sha256(run(['nft','-j','-s','list','ruleset']).stdout.encode()).hexdigest()

def call(node,path,body=None,peer='operator',reject=False):
    # Real mTLS client in the controller netns, addressing the real node IP.
    code='''import json,sys,urllib.error
from fleetweft.tls import TLS
try:
 t=TLS(sys.argv[1]+'/ca.crt',sys.argv[1]+'/'+sys.argv[2]+'.crt',sys.argv[1]+'/'+sys.argv[2]+'.key')
 print(json.dumps(t.request(sys.argv[3],sys.argv[4],json.loads(sys.argv[5]))))
except urllib.error.HTTPError as e: print(json.dumps({'status':e.code}));sys.exit(17)
except (OSError,urllib.error.URLError) as e: print(json.dumps({'transport':type(e).__name__}));sys.exit(18)
'''
    p=run(['ip','netns','exec','fw_ctl',PY,'-I','-c',code,str(CONF),peer,'https://'+IPS[node]+':'+str(PORT),path,json.dumps(body)],check=False,timeout=5)
    if reject:
        assert p.returncode==17 and json.loads(p.stdout)=={'status':reject if type(reject) is int else 409},(p.returncode,p.stdout,p.stderr)
    else:
        if p.returncode: raise RuntimeError('mTLS request '+node+path+': '+p.stdout+p.stderr)
    return json.loads(p.stdout)

def status(): return call('controller','/status')
def ns(node): return call(node,'/status')
def work(node):
    out=call(node,'/work?x=7&challenge=evidence'); assert out['result']==14,out
    return out

def phase(name):
    return wait(lambda: (s if (s:=status())['fleet']['phase']==name else None))

def topology():
    # This root fixture only creates isolated interfaces, not host routing/firewall.
    ownership=Ownership(ROOT,run); ownership.start_topology(bootid())
    for name in ['ctl','a','b','c']: ownership.add_namespace('fw_'+name)
    run(['ip','-n','fw_ctl','link','add','br0','type','bridge'])
    run(['ip','-n','fw_ctl','addr','add',IPS['controller']+'/24','dev','br0'])
    run(['ip','-n','fw_ctl','link','set','br0','up'])
    for name in ['ctl','a','b','c']: run(['ip','-n','fw_'+name,'link','set','lo','up'])
    for n in 'abc':
        ownership.add_veth('fwp'+n,'fwn'+n)
        run(['ip','link','set','fwp'+n,'netns','fw_ctl']); run(['ip','link','set','fwn'+n,'netns','fw_'+n])
        run(['ip','-n','fw_ctl','link','set','fwp'+n,'master','br0']); run(['ip','-n','fw_ctl','link','set','fwp'+n,'up'])
        run(['ip','-n','fw_'+n,'addr','add',IPS[n]+'/24','dev','fwn'+n]); run(['ip','-n','fw_'+n,'link','set','fwn'+n,'up'])
    before={'boot_id':bootid(),'states':{}}
    import sqlite3
    for name in ['controller','a','b','c']:
        db=STATE/name/'state.sqlite'
        if db.exists():
            with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as con:
                before['states'][name]=json.loads(con.execute('select data from snapshot').fetchone()[0])
    (STATE/'prestart.json').write_text(json.dumps(before))

def reset():
    run(['systemctl','stop',*UNITS])
    for n in ['controller','a','b','c']:
        shutil.rmtree(STATE/n,ignore_errors=True); (STATE/n).mkdir(mode=0o700)
    c=Coordinator(STATE/'controller',json.loads((CONF/'controller.json').read_text())['catalog']); c.store.close()
    for n in 'abc':
        config=json.loads((CONF/(n+'.json')).read_text()); uid=provision(config)
        cache=Artifacts(config['cache'],config['signing_public_key'],config['catalog'])
        sha=config['catalog']['v1']; cache.install((ROOT/'bundles'/(sha+'.zip')).read_bytes(),'v1')
        c=Coordinator(STATE/'controller',config['catalog']); c.call('enroll',dict(node=n,node_uuid=uid)); c.store.close()
    run(['chown','-R','fleetweft:fleetweft',STATE])
    for n in 'abc':
        checkpoint=Path('/etc/systemd/system/fleetweft-node@'+n+'.service.d/checkpoint.conf')
        checkpoint.unlink(missing_ok=True)
    run(['systemctl','daemon-reload']); run(['systemctl','reset-failed',*UNITS],check=False)
    run(['systemctl','start',*UNITS]); wait(lambda: all(r['status'] for r in status()['registry'].values()))
    for n in 'abc': assert work(n)['release']=='v1'

def deploy(release='v2'): return call('controller','/deploy',dict(release=release))
def capture(name,started,**extra):
    s=status(); workers={n:work(n) for n in 'abc' if extra.get('offline')!=n and n not in extra.get('unavailable',[])}
    row=dict(name=name,passed=True,seconds=time.monotonic()-started,status=s,serving=workers,**extra)
    CASES.append(row); (STATE/'cases.json').write_text(json.dumps(CASES)); return row

def setup():
    preflight(ROOT,STATE,CONF,KEYS,run,uploaded=True)
    ownership=Ownership(ROOT,run)
    system=Path('/etc/systemd/system')
    ownership.begin([STATE,CONF,KEYS,*[system/n for n in ('fleetweft-controller.service','fleetweft-node@.service','fleetweft-fixture.service','fleetweft-fixture-proxy.service')],*[system/(u+'.d') for u in UNITS],*[system/'multi-user.target.wants'/u for u in ['fleetweft-fixture.service',*UNITS]]])
    ownership.mkdir(STATE); ownership.mkdir(CONF); ownership.mkdir(KEYS,mode=0o700)
    run(['useradd','--system','--user-group','--no-create-home','--shell','/usr/sbin/nologin','fleetweft'])
    ownership.remember_account()
    credentials(KEYS,IPS); catalog=bundles(ROOT/'bundles',KEYS/'sign.key')
    for name in ['ca.crt','sign.pub']+[n+ext for n in IPS for ext in ('.crt','.key')]:
        shutil.copyfile(KEYS/name,CONF/name); (CONF/name).chmod(0o600 if name.endswith('.key') else 0o644)
    for name in ['controller','a','b','c']:
        config=dict(role='controller' if name=='controller' else 'node',state=str(STATE/name),port=PORT,listen=IPS[name],
                    catalog=catalog,ca=str(CONF/'ca.crt'),cert=str(CONF/(name+'.crt')),key=str(CONF/(name+'.key')),
                    signing_public_key=str(CONF/'sign.pub'),cache=str(STATE/name/'cache'),node=name,
                    controller='https://'+IPS['controller']+':'+str(PORT),bundles=str(ROOT/'bundles'),samples=3,window=.15)
        (CONF/(name+'.json')).write_text(json.dumps(config))
    run(['chown','-R','fleetweft:fleetweft',CONF])
    run(['chown','root:root',CONF/'operator.key'])
    assert run(['runuser','-u','fleetweft','--','test','-r',CONF/'operator.key'],check=False).returncode==1
    assert run(['runuser','-u','fleetweft','--','test','-r',KEYS/'sign.key'],check=False).returncode!=0
    for name in ('fleetweft-controller.service','fleetweft-node@.service'):
        ownership.write(Path('/etc/systemd/system')/name,(SOURCE/'deploy'/name).read_text())
    for name in ['controller','a','b','c']:
        unit=UNITS[0] if name=='controller' else 'fleetweft-node@'+name+'.service'
        d=Path('/etc/systemd/system')/(unit+'.d'); ownership.mkdir(d)
        ownership.write(d/'fixture.conf','[Unit]\nRequires=fleetweft-fixture.service\nAfter=fleetweft-fixture.service\n[Service]\nNetworkNamespacePath=/run/netns/fw_'+('ctl' if name=='controller' else name)+'\n')
    ownership.write(Path('/etc/systemd/system/fleetweft-fixture.service'),'[Unit]\nDescription=Isolated Fleetweft VM fixture\nBefore='+ ' '.join(UNITS)+'\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart='+PY+' -I '+str(SOURCE/'tools/mvp_guest.py')+' topology\n[Install]\nWantedBy=multi-user.target\n')
    ownership.write(system/'fleetweft-fixture-proxy.service',
        '[Unit]\nDescription=Fleetweft authorization-reply fault fixture\nRequires=fleetweft-fixture.service\nAfter=fleetweft-fixture.service\n[Service]\nUser=fleetweft\nGroup=fleetweft\nNetworkNamespacePath=/run/netns/fw_ctl\nKillMode=control-group\nExecStart='+PY+' -I '+str(SOURCE/'tools/mvp_fault_proxy.py')+'\n')
    run(['systemctl','daemon-reload']); run(['systemctl','start','fleetweft-fixture.service'])
    reset()
    run(['systemctl','enable','fleetweft-fixture.service',*UNITS])
    ownership.load()  # topology runs in a separate systemd process and updates the ledger.
    for unit in ['fleetweft-fixture.service',*UNITS]:
        ownership.remember_link(system/'multi-user.target.wants'/unit)
    (STATE/'root-firewall.sha').write_text(firewall())


def kill_serving(snapshot):
    import signal
    from fleetweft.node import identity
    matching=[child for child in snapshot['workers'] if snapshot['route']['worker'].encode() in Path(f"/proc/{child['pid']}/cmdline").read_bytes().split(b'\0')]
    assert len(matching)==1
    child=matching[0]; assert identity(child['pid'])==child
    fd=os.pidfd_open(child['pid'])
    try:
        assert identity(child['pid'])==child; signal.pidfd_send_signal(fd,signal.SIGKILL)
    finally: os.close(fd)


def scenarios():
    # Actual shipping-unit / installed-source identity observations.
    from importlib import import_module
    installed={}
    for p in sorted((SOURCE/'fleetweft').glob('*.py')):
        m=import_module('fleetweft.'+p.stem) if p.stem!='__init__' else import_module('fleetweft')
        path=Path(m.__file__); assert path.is_relative_to(ROOT/'venv')
        assert path.read_bytes()==p.read_bytes(); installed[p.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    units={u:props(u) for u in UNITS}
    unit_files={name:hashlib.sha256((Path('/etc/systemd/system')/name).read_bytes()).hexdigest() for name in ('fleetweft-controller.service','fleetweft-node@.service')}
    for u,values in units.items():
        assert values['User']=='fleetweft' and values['NoNewPrivileges']=='yes' and values['CapabilityBoundingSet']==''
        assert '-I -m fleetweft.mvp serve' in values['ExecStart'] and values['KillMode']=='control-group'
    began=time.monotonic(); deploy(); s=phase('COMPLETED')
    events=s['events']; settled=next(e['sequence'] for e in events if e['kind']=='SETTLED' and e['node']=='a')
    assert all(e['sequence']>settled for e in events if e['kind']=='GRANT' and e['node']!='a')
    assert all(work(n)['release']=='v2' for n in 'abc'); capture('three-node-canary',began)

    reset(); began=time.monotonic(); deploy('bad'); phase('PAUSED'); wait(lambda: status()['active'] is None)
    assert status()['fleet']['targets']['a']=='FAILED' and not status()['fleet']['canary_passed']
    assert not any(e['kind']=='GRANT' and e['node']!='a' for e in status()['events'])
    capture('failed-canary-pauses',began)

    reset(); began=time.monotonic(); deploy('crash'); phase('PAUSED'); wait(lambda: status()['active'] is None)
    assert all(work(n)['release']=='v1' for n in 'abc')
    assert status()['fleet']['targets']['a']=='FAILED'
    capture('startup-failure-restores',began)

    reset(); began=time.monotonic(); deploy('badb'); phase('PAUSED'); wait(lambda: status()['active'] is None)
    assert work('a')['release']=='badb' and work('b')['release']=='v1'
    assert status()['fleet']['targets']['b']=='FAILED'
    run(['systemctl','stop','fleetweft-node@c.service']); time.sleep(2.1)
    call('controller','/rollback',{}); wait(lambda: status()['fleet']['targets']['a']=='SUCCEEDED')
    assert status()['fleet']['phase']!='ROLLED_BACK'
    partial=status(); run(['systemctl','start','fleetweft-node@c.service']); phase('ROLLED_BACK')
    assert all(work(n)['release']=='v1' for n in 'abc'); capture('later-failure-partial-rollback',began,partial=partial)

    reset(); began=time.monotonic(); run(['systemctl','stop','fleetweft-node@c.service']); time.sleep(2.1)
    deploy(); wait(lambda: status()['fleet']['targets']['b']=='SUCCEEDED')
    wait(lambda: status()['fleet']['targets']['c']=='DEFERRED')
    deploy('v3'); wait(lambda: status()['fleet']['targets']['b']=='SUCCEEDED')
    run(['systemctl','start','fleetweft-node@c.service']); phase('COMPLETED')
    s=status(); assert s['history'][0]['phase']=='SUPERSEDED_INCOMPLETE'
    assert not any(e['kind']=='GRANT' and e['node']=='c' and e['release']=='v2' for e in s['events'])
    assert all(work(n)['release']=='v3' for n in 'abc'); capture('offline-latest-catch-up',began)

    reset(); began=time.monotonic()
    d=Path('/etc/systemd/system/fleetweft-node@a.service.d/checkpoint.conf')
    d.write_text('[Service]\nEnvironment=FLEETWEFT_CHECKPOINT=staged\n')
    run(['systemctl','daemon-reload']); run(['systemctl','restart','fleetweft-node@a.service']); wait(lambda: ns('a'))
    deploy(); wait(lambda: (STATE/'a/checkpoint').exists())
    token=status()['active']['token']; run(['ip','-n','fw_ctl','link','set','fwpa','down'])
    call('controller','/pause',{}); time.sleep(2.2)
    assert status()['active']['token']==token and not any(e['kind']=='GRANT' and e['node']!='a' for e in status()['events'])
    held=status(); (STATE/'a/release-checkpoint').touch(); run(['ip','-n','fw_ctl','link','set','fwpa','up'])
    wait(lambda: status()['active'] is None); assert work('a')['release']=='v1'
    capture('partition-retains-grant',began,held=held)

    reset(); began=time.monotonic(); deploy(); phase('COMPLETED')
    old=props('fleetweft-node@b.service'); oldinc=ns('b')['incarnation']
    started=time.monotonic(); run(['systemctl','kill','--kill-whom=main','--signal=SIGKILL','fleetweft-node@b.service'])
    restored=wait(lambda: (v if (v:=work('b'))['incarnation']!=oldinc else None))
    restart_seconds=time.monotonic()-started
    new=props('fleetweft-node@b.service'); assert old['InvocationID']!=new['InvocationID'] and restored['release']=='v2'
    ctlold=props(UNITS[0]); run(['systemctl','kill','--kill-whom=main','--signal=SIGKILL',UNITS[0]])
    wait(lambda: status()); assert props(UNITS[0])['InvocationID']!=ctlold['InvocationID']
    assert all(work(n)['release']=='v2' for n in 'abc')
    capture('agent-controller-sigkill',began,restart_seconds=restart_seconds,old_unit=old,new_unit=new,old_controller=ctlold,new_controller=props(UNITS[0]))

    # AuthN/AuthZ and artifact corruption exercise the real HTTPS boundary.
    reset(); began=time.monotonic()
    rejects=[call('controller','/deploy',{'release':'v2'},peer='a',reject=True),
             call('controller','/poll',{'node':'b'},peer='a',reject=True),call('a','/activate',{},reject=True)]
    no_cert=run(['ip','netns','exec','fw_ctl',PY,'-I','-c',
                "import ssl,urllib.request; urllib.request.urlopen('https://192.0.2.1:19443/status',context=ssl.create_default_context(cafile='/etc/fleetweft/ca.crt'),timeout=2)"],check=False)
    assert no_cert.returncode!=0 and ('certificate required' in no_cert.stderr.lower() or 'alert' in no_cert.stderr.lower())
    wrong_ca=run(['ip','netns','exec','fw_ctl',PY,'-I','-c',
                  "import ssl,urllib.request; c=ssl.create_default_context(); c.load_cert_chain('/etc/fleetweft/operator.crt','/etc/fleetweft/operator.key'); urllib.request.urlopen('https://192.0.2.1:19443/status',context=c,timeout=2)"],check=False)
    assert wrong_ca.returncode!=0 and 'CERTIFICATE_VERIFY_FAILED' in wrong_ca.stderr
    catalog=json.loads((CONF/'controller.json').read_text())['catalog']; path=ROOT/'bundles'/(catalog['v2']+'.zip')
    original=path.read_bytes(); path.write_bytes(original[:-5]); deploy(); phase('PAUSED'); wait(lambda: status()['active'] is None)
    assert all(work(n)['release']=='v1' for n in 'abc'); path.write_bytes(original)
    capture('mtls-and-tampered-artifact',began,rejections=rejects,no_client_certificate_rejected=True,untrusted_ca_rejected=True)

    # Delayed executor invokes the same Node mutation methods and real signed worker.
    reset(); began=time.monotonic(); config=json.loads((CONF/'a.json').read_text())
    tmp=STATE/'delayed'; provision({'state':str(tmp)})
    cache=Artifacts(tmp/'cache',CONF/'sign.pub',catalog)
    for rel in ('v1','v2','v3'): cache.install((ROOT/'bundles'/(catalog[rel]+'.zip')).read_bytes(),rel)
    node=Node(tmp,'a','unused',cache,secure=True)
    try:
        def token(gen,rel): return dict(node='a',generation=gen,release=rel,baseline='v1',digest=catalog[rel],epoch=1,op=str(gen))
        t1=token(1,'v2'); t2=token(2,'v3'); incarnation=node.incarnation
        node.call('accept',dict(token=t1,incarnation=incarnation)); node.call('activate',dict(token=t1,incarnation=incarnation))
        preflight=node.snapshot(); node.call('cancel',dict(token=t1,incarnation=incarnation))
        node.call('accept',dict(token=t2,incarnation=incarnation)); node.call('activate',dict(token=t2,incarnation=incarnation))
        before=node.work(7,'before-late')
        try: node.call('activate',dict(token=preflight['token'],incarnation=incarnation))
        except ValueError as exc: assert str(exc)=='Stale executor'
        else: raise AssertionError('Delayed executor was allowed')
        after=node.work(7,'after-late'); assert before['route']==after['route'] and after['release']=='v3' and after['result']==14
        capture('delayed-executor-real-backend',began,preflight=preflight,before=before,after=after)
    finally: node.close()

    reset(); began=time.monotonic()
    initial=status()['registry']['a']; old_status=ns('a'); old_probe=work('a')
    deploy(); phase('COMPLETED')
    stale=call('controller','/poll',dict(node='a',sequence=initial['poll_sequence'],status=old_status,probe=old_probe),peer='a',reject=True)
    assert status()['registry']['a']['status']['committed']=='v2'
    deploy('v3'); phase('COMPLETED'); baseline=status()['fleet']['baseline']
    assert baseline=={n:'v2' for n in 'abc'}
    call('controller','/rollback',{}); phase('ROLLED_BACK')
    assert all(work(n)['release']=='v2' for n in 'abc')
    capture('reordered-poll-preserves-baseline',began,stale_rejection=stale,baseline=baseline)

    for decision in ('pause','rollback'):
        reset(); began=time.monotonic()
        proxy=STATE/'proxy'; shutil.rmtree(proxy,ignore_errors=True); proxy.mkdir()
        run(['chown','fleetweft:fleetweft',proxy])
        cfg=CONF/'a.json'; config=json.loads(cfg.read_text()); original_controller=config['controller']
        config['controller']='https://192.0.2.1:19444'; cfg.write_text(json.dumps(config))
        run(['systemctl','restart','fleetweft-fixture-proxy.service','fleetweft-node@a.service'])
        wait(lambda: status()['registry']['a']['incarnation']==ns('a')['incarnation'])
        deploy(); wait(lambda: (proxy/'lost.json').exists())
        authorization=json.loads((proxy/'lost.json').read_text()); current=ns('a')
        assert current['phase']=='OBSERVING' and authorization['active']['commit_authorized']
        call('controller','/'+decision,{})
        blocked=status(); assert blocked['active']['commit_authorized'] and blocked['paused']
        (proxy/'release').touch()
        if decision=='pause':
            wait(lambda: status()['active'] is None)
            assert status()['paused'] and work('a')['release']=='v2'
            assert not any(e['kind']=='GRANT' and e['node']!='a' for e in status()['events'])
        else:
            phase('ROLLED_BACK'); assert all(work(n)['release']=='v1' for n in 'abc')
        approvals=[json.loads(line) for line in (proxy/'approvals.jsonl').read_text().splitlines()]
        assert len(approvals)>=2 and approvals[0]==approvals[1]==authorization
        capture('lost-authorization-'+decision,began,authorization=authorization,approvals=approvals,blocked=blocked)
        run(['systemctl','stop','fleetweft-fixture-proxy.service'])
        config['controller']=original_controller; cfg.write_text(json.dumps(config))

    reset(); began=time.monotonic()
    d=Path('/etc/systemd/system/fleetweft-node@a.service.d/checkpoint.conf')
    d.write_text('[Service]\nEnvironment=FLEETWEFT_CHECKPOINT=after_commit\n')
    run(['systemctl','daemon-reload']); run(['systemctl','restart','fleetweft-node@a.service']); wait(lambda: ns('a'))
    deploy(); wait(lambda: (STATE/'a/checkpoint').exists())
    committed=ns('a'); assert committed['phase']=='COMMITTED' and work('a')['release']=='v2'
    kill_serving(committed)
    failure=call('a','/work',reject=503); (STATE/'a/release-checkpoint').touch()
    wait(lambda: status()['active'] is None)
    paused=status(); assert paused['paused'] and not paused['fleet']['canary_passed']
    assert paused['fleet']['attempts'][-1]['result']=='COMMITTED' and not paused['fleet']['attempts'][-1]['serving_verified']
    assert not any(e['kind']=='GRANT' and e['node']!='a' for e in paused['events'])
    capture('committed-canary-probe-failure',began,unavailable=['a'],failed_http=failure,committed=committed)

    reset(); began=time.monotonic()
    d.write_text('[Service]\nEnvironment=FLEETWEFT_CHECKPOINT=after_cancel\n')
    run(['systemctl','daemon-reload']); run(['systemctl','restart','fleetweft-node@a.service']); wait(lambda: ns('a'))
    deploy('bad'); wait(lambda: (STATE/'a/checkpoint').exists())
    restored=ns('a'); assert restored['phase']=='FAILED_RESTORED' and work('a')['release']=='v1'
    kill_serving(restored); failure=call('a','/work',reject=503); (STATE/'a/release-checkpoint').touch()
    wait(lambda: status()['active'] and status()['active'].get('restore_unverified'))
    held=status(); assert held['occupancy']['state']=='UNKNOWN' and held['active']['token']==restored['token']
    run(['systemctl','restart','fleetweft-node@a.service'])
    wait(lambda: status()['active'] is None); assert work('a')['release']=='v1' and status()['paused']
    capture('unverified-restore-retains-slot',began,held=held,failed_http=failure,restored=restored)

    # Fixed sample count, ALL outcomes retained; service processes' RSS separately.
    reset(); deploy(); phase('COMPLETED'); began=time.monotonic(); requests=[]
    # One persistent measurement driver; each timed operation still includes a
    # new TLS handshake and response read, but NOT interpreter/netns startup.
    driver="""import json,time
from fleetweft.tls import TLS
t=TLS('/etc/fleetweft/ca.crt','/etc/fleetweft/operator.crt','/etc/fleetweft/operator.key')
rows=[]
for i in range(30):
 n='abc'[i%3]; started=time.monotonic()
 try:
  v=t.request('https://192.0.2.'+str(11+i%3)+':19443','/work?x=7&challenge=measurement')
  out=dict(ok=v['release']=='v2' and v['result']==14,release=v['release'],result=v['result'])
 except Exception as e: out=dict(ok=False,error=type(e).__name__)
 rows.append(dict(index=i,node=n,seconds=time.monotonic()-started,**out))
print(json.dumps(rows))
"""
    requests=json.loads(run(['ip','netns','exec','fw_ctl',PY,'-I','-c',driver]).stdout)
    rss={}
    for u in UNITS:
        pid=int(props(u)['MainPID']); fields=dict(line.split(':',1) for line in Path(f'/proc/{pid}/status').read_text().splitlines() if ':' in line)
        rss[u]={'pid':pid,'rss_kib':int(fields['VmRSS'].split()[0])}
    worker_rss={}
    for n in 'abc':
        current=ns(n); worker_rss[n]=[]
        for child in current['workers']:
            fields=dict(line.split(':',1) for line in Path(f"/proc/{child['pid']}/status").read_text().splitlines() if ':' in line)
            worker_rss[n].append(dict(**child,rss_kib=int(fields['VmRSS'].split()[0])))
        assert len(worker_rss[n])==1
    assert all(r['ok'] for r in requests)
    capture('measured-requests',began,requests=requests,process_rss=rss,worker_rss=worker_rss)

    # Prepare a pending candidate plus two durable committed nodes for REAL reboot.
    reset(); deploy(); phase('COMPLETED')
    d=Path('/etc/systemd/system/fleetweft-node@a.service.d/checkpoint.conf')
    d.write_text('[Service]\nEnvironment=FLEETWEFT_CHECKPOINT=after_route\n')
    run(['systemctl','daemon-reload']); run(['systemctl','restart','fleetweft-node@a.service']); wait(lambda: ns('a'))
    deploy('v3'); wait(lambda: (STATE/'a/checkpoint').exists())
    pending=ns('a'); assert pending['phase']=='ACTIVATING' and pending['committed']=='v2' and work('a')['release']=='v3'
    pre=dict(boot_id=bootid(),pending=pending,serving=work('a'),controller=status(),units={u:props(u) for u in UNITS})
    (STATE/'reboot-before.json').write_text(json.dumps(pre))
    result=dict(passed=True,source=manifest(SOURCE),source_sha256=fingerprint(manifest(SOURCE)),
                installed=installed,units=units,unit_files=unit_files,cases=CASES,reboot_before=pre,environment=dict(kernel=os.uname().release,systemd=run(['systemd','--version']).stdout.splitlines()[0]))
    (STATE/'phase-one.json').write_text(json.dumps(result))
    return result


def after_reboot():
    result=json.loads((STATE/'phase-one.json').read_text()); pre=json.loads((STATE/'reboot-before.json').read_text())
    observed=json.loads((STATE/'prestart.json').read_text()); assert bootid()!=pre['boot_id']==result['reboot_before']['boot_id']
    before=observed['states']['a']; assert before['phase']=='ACTIVATING' and before['committed']=='v2' and before['accepted']==pre['pending']['token']
    # This is read by the topology unit BEFORE the agent is started in the new boot.
    assert observed['boot_id']==bootid()
    wait(lambda: status()['active'] is None)
    s=status(); assert s['paused'] and s['fleet']['phase']=='PAUSED'
    serving={n:work(n) for n in 'abc'}; assert all(v['release']=='v2' for v in serving.values())
    assert ns('a')['phase']=='FAILED_RESTORED'
    units={u:props(u) for u in UNITS}; assert all(units[u]['InvocationID']!=pre['units'][u]['InvocationID'] for u in UNITS)
    result['reboot_after']=dict(boot_id=bootid(),prestart=observed,status=s,serving=serving,units=units,node_status={n:ns(n) for n in 'abc'})
    result['power_loss_tested']=False; result['boot_zero_gap_tested']=False
    return result


def cleanup():
    ownership=Ownership(ROOT,run)
    expected=(STATE/'root-firewall.sha').read_text() if (STATE/'root-firewall.sha').exists() else None
    if expected is not None and expected!=firewall():
        raise RuntimeError('Unrelated root ruleset changed')
    return ownership.cleanup([*UNITS,'fleetweft-fixture.service','fleetweft-fixture-proxy.service'],firewall)


if __name__=='__main__':
    mode=sys.argv[1]
    try:
        if mode=='topology': topology()
        elif mode=='setup': setup(); print(json.dumps(scenarios()))
        elif mode=='after': print(json.dumps(after_reboot()))
        elif mode=='cleanup': print(json.dumps(cleanup()))
        else: raise ValueError(mode)
    except BaseException:
        traceback.print_exc(); sys.exit(1)
