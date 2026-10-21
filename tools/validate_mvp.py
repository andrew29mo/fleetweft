"""Dedicated stopped Colima VM only; never runs experiments on the host network."""
import argparse
import base64
import datetime
import fcntl
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from .evidence import ROOT,manifest,fingerprint
from .mvp_report import verify,render,controls


def main():
    p=argparse.ArgumentParser();p.add_argument('--colima-home',required=True);p.add_argument('--toolchain',required=True)
    p.add_argument('--profile',default='relay');p.add_argument('--output',required=True);a=p.parse_args()
    out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):p.error('New empty output required')
    home=Path(a.colima_home).resolve();bins=Path(a.toolchain).resolve();colima=str(bins/'colima')
    fd=os.open(home/('.rulemoor-'+a.profile+'.lock'),os.O_CREAT|os.O_RDWR,0o600);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    source=manifest();rid=secrets.token_hex(8)
    v={'passed':False,'run_id':rid,'recorded_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'source':source,'source_sha256':fingerprint(source),'source_changed':False,'stages':[]}
    env=dict(os.environ,COLIMA_HOME=str(home),PATH=str(bins)+os.pathsep+os.environ.get('PATH',''))
    env.pop('DOCKER_CONTEXT',None);started=uploaded=False
    def persist():
        (out/'evidence.json').write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
        (out/'report.html').write_text(render(v))
    def call(name,args,timeout=60,check=True,**kw):
        began=time.monotonic();proc=subprocess.Popen(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True,**kw)
        timed_out=False
        try:stdout,stderr=proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out=True;os.killpg(proc.pid,signal.SIGKILL);stdout,stderr=proc.communicate(timeout=5)
        except BaseException:
            os.killpg(proc.pid,signal.SIGKILL);proc.communicate(timeout=5);raise
        finally:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        (out/'private-logs').mkdir(exist_ok=True);(out/'private-logs'/ (name+'.log')).write_text(stdout+stderr)
        v['stages'].append({'name':name,'exit_code':proc.returncode,'timed_out':timed_out,'seconds':time.monotonic()-began});persist()
        if check and (proc.returncode!=0 or timed_out):raise RuntimeError(name+' failed or timed out')
        return stdout,proc.returncode,timed_out
    def ssh(name,args,**kw):return call(name,[colima,'--profile',a.profile,'ssh','--',*args],**kw)
    def state(name):
        stdout,_,_=call(name,[colima,'list','--json']);rows=[json.loads(x) for x in stdout.splitlines()]
        matches=[r for r in rows if r['name']==a.profile];assert len(matches)==1
        return matches[0]['status']
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        call('native-unit',[sys.executable,'-m','tools.unit','--output',str(out/'native-unit.json')],cwd=ROOT,timeout=90)
        v['native_unit']=json.loads((out/'native-unit.json').read_text())
        call('mutations',[sys.executable,'-m','tools.mutations','--output',str(out/'mutations.json')],cwd=ROOT,timeout=90)
        v['mutations']=json.loads((out/'mutations.json').read_text())
        v['vm_initial']=state('vm-initial');assert v['vm_initial']=='Stopped';started=True
        call('vm-start',[colima,'start',a.profile,'--cpu','4','--memory','6','--disk','30','--vm-type','vz','--runtime','docker','--mount','none','--activate=false','--ssh-config=false','--ssh-agent=false','--vz-rosetta=false','--binfmt=false'],timeout=240)
        ssh('preflight',['sudo','sh','-c','test ! -e /opt/fleetweft && test ! -e /var/lib/fleetweft && test ! -e /etc/fleetweft && test ! -e /etc/systemd/system/fleetweft-controller.service && test "$(cat /proc/1/comm)" = systemd && test -z "$(docker ps -q)"'])
        with tempfile.TemporaryDirectory() as tmp:
            snap=Path(tmp)
            for f in source:
                dst=snap/f;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/f,dst)
            call('wheel-build',[sys.executable,'-m','build','--wheel','--no-isolation','--outdir',str(snap/'wheel')],cwd=snap,timeout=90)
            wheel=next((snap/'wheel').glob('*.whl'))
            buffer=io.BytesIO()
            with tarfile.open(fileobj=buffer,mode='w:gz') as tar:
                for f in source:tar.add(snap/f,arcname='source/'+f,recursive=False)
                tar.add(wheel,arcname=wheel.name,recursive=False)
            code="import pathlib,sys,tarfile,io,base64;p=pathlib.Path('/opt/fleetweft');p.mkdir();(p/'owner').write_text(sys.argv[1]);tarfile.open(fileobj=io.BytesIO(base64.b64decode(sys.stdin.read()))).extractall(p,filter='data')"
            transfer=snap/'transfer';transfer.write_text(base64.b64encode(buffer.getvalue()).decode())
            uploaded=True
            with transfer.open() as stream:ssh('upload',['sudo','python3','-c',code,rid],stdin=stream)
        ssh('install',['sudo','sh','-c','python3 -m venv /opt/fleetweft/venv && /opt/fleetweft/venv/bin/pip install --no-index /opt/fleetweft/*.whl'],timeout=90)
        stdout,rc,timed=ssh('guest-setup',['sudo','/opt/fleetweft/venv/bin/python','-I','/opt/fleetweft/source/tools/mvp_guest.py','setup'],timeout=360,check=False)
        v['guest']=json.loads(stdout);assert rc==0 and not timed and v['guest']['passed']
        stdout,_,_=ssh('linux-unit',['sudo','sh','-c','cd /opt/fleetweft/source && /opt/fleetweft/venv/bin/python -m tools.unit --output /opt/fleetweft/linux-unit.json'],timeout=90)
        stdout,_,_=ssh('linux-unit-read',['sudo','cat','/opt/fleetweft/linux-unit.json']);v['linux_unit']=json.loads(stdout)
        call('vm-orderly-stop',[colima,'stop',a.profile],timeout=120)
        assert state('vm-between')=='Stopped'
        call('vm-restart',[colima,'start',a.profile,'--activate=false','--ssh-config=false'],timeout=240)
        stdout,_,_=ssh('guest-after-reboot',['sudo','/opt/fleetweft/venv/bin/python','-I','/opt/fleetweft/source/tools/mvp_guest.py','after'],timeout=90)
        v['guest']=json.loads(stdout)
        stdout,_,_=ssh('guest-cleanup',['sudo','/opt/fleetweft/venv/bin/python','-I','/opt/fleetweft/source/tools/mvp_guest.py','cleanup'],timeout=60)
        v['cleanup']=json.loads(stdout)
        v['passed']=True
    except BaseException as exc:v['error']=type(exc).__name__+': '+str(exc).replace(str(ROOT),'<checkout>').replace(str(home),'<vm-home>')
    finally:
        for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,signal.SIG_IGN)
        if uploaded:
            try:
                # Guest normally cleans its fixture. On timeout, stop owned units
                # before deleting the run snapshot; never clear unrelated paths.
                code="import pathlib,sys,shutil,subprocess;p=pathlib.Path('/opt/fleetweft');assert (p/'owner').read_text()==sys.argv[1];s=pathlib.Path('/var/lib/fleetweft');subprocess.run([str(p/'venv/bin/python'),'-I',str(p/'source/tools/mvp_guest.py'),'cleanup'],check=True) if s.exists() else None;shutil.rmtree(p)"
                ssh('remove',['sudo','python3','-c',code,rid]);v['snapshot_removed']=True
            except BaseException as exc:v['cleanup_error']=str(exc)
        if started:
            try:call('vm-stop',[colima,'stop',a.profile],timeout=120);v['vm_final']=state('vm-final')
            except BaseException as exc:v['vm_cleanup_error']=str(exc)
        v['source_changed']=manifest()!=source
        if v['passed']:
            try:verify(v,source);v['controls']=controls(v,source)
            except BaseException as exc:v.update(passed=False,verification_error=type(exc).__name__)
        persist();os.close(fd)
    print(json.dumps({k:v.get(k) for k in ('passed','run_id','error','cleanup_error','verification_error','vm_final')}))
    raise SystemExit(0 if v['passed'] else 1)


if __name__=='__main__':main()
