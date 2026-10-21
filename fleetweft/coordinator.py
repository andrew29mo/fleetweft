"""Single-controller durable three-node rollout, reusing the execution protocol."""
import copy
import secrets
import time
from .core import Controller
from .store import require

class BufferedStore:
    def __init__(self, value): self.value=copy.deepcopy(value)
    def read(self): return copy.deepcopy(self.value)
    def save(self, value): self.value=copy.deepcopy(value)

class Coordinator(Controller):
    def __init__(self, root, digests, samples=3, window=.1, freshness=2):
        super().__init__(root,samples,window,digests)
        self.freshness=freshness
        s=self.store.read()
        s.setdefault('registry',{}); s.setdefault('fleet',None); s.setdefault('history',[])
        s.setdefault('events',[]); s.setdefault('event_seq',0)
        for n in s['registry'].values(): n['seen_ns']=None
        if s['fleet'] and s['fleet']['phase'] not in ('COMPLETED','ROLLED_BACK'):
            s['paused']=True; s['fleet']['phase']='PAUSED'
        self.store.save(s)

    def base(self, action, p): return super().call(action,p)

    def event(self, kind, **fields):
        s=self.store.read(); require(len(s['events'])<2048,'Event journal full')
        s['event_seq']+=1
        s['events'].append(dict(sequence=s['event_seq'],kind=kind,**fields))
        self.store.save(s)

    def call(self, action, p, peer='operator'):
        # Core grant settlement and fleet progress commit in the SAME transaction.
        # No response leaves an intermediate active=None snapshot on disk.
        with self.lock:
            durable=self.store; buffer=BufferedStore(durable.read()); self.store=buffer
            try:
                result=self.dispatch(action,p,peer)
                durable.save(buffer.read())
                return result
            finally: self.store=durable

    def dispatch(self, action, p, peer):
        s=self.store.read()
        if action=='poll':
            require(peer in s['registry'] and p['node']==peer,'Wrong authenticated node')
            return self.poll(p)
        if action=='authorize_commit':
            require(peer in s['registry'] and p['token']['node']==peer,'Wrong authenticated node')
            approved=self.base(action,p)['active']
            return {'active':{'token':approved['token'],'commit_authorized':approved['commit_authorized']}}
        require(peer=='operator','Operator identity required')
        if action=='status':
            s['observations']={n:dict(fresh=self.fresh(r),healthy=r['healthy'] and self.fresh(r)) for n,r in s['registry'].items()}
            a=s['active']
            s['occupancy']=None if a is None else dict(node=a['token']['node'],
                state='ACTIVE' if self.fresh(s['registry'][a['token']['node']]) and not a.get('restore_unverified') else 'UNKNOWN')
            return s
        if action=='enroll':
            require(s['fleet'] is None and s['active'] is None, 'Enrollment requires an unused controller')
            name=p['node']; require(name in ('a','b','c') and name not in s['registry'],'Invalid node enrollment')
            require(isinstance(p['node_uuid'],str) and len(p['node_uuid'])==32,'Invalid identity')
            s['registry'][name]=dict(node_uuid=p['node_uuid'],boot_sequence=-1,incarnation=None,
                                      seen_ns=None,status=None,healthy=False,poll_sequence=0)
            self.store.save(s); return {'enrolled':name}
        if action=='deploy':
            require(s['active'] is None and not s['paused'], 'Unsettled or paused')
            require(set(s['registry'])=={'a','b','c'},'Three enrolled nodes required')
            require(p['release'] in self.digests,'Unknown release')
            require(p.get('canary','a') in s['registry'],'Unknown canary')
            require(all(r['status'] is not None for r in s['registry'].values()),'All initial baselines must be observed')
            require(len(s['history'])<8,'Fleet history capacity reached')
            if s['fleet']:
                old=copy.deepcopy(s['fleet'])
                require(old['phase'] in ('COMPLETED','ROLLED_BACK','CONVERGING'),'Cannot supersede failed rollout')
                if old['phase']=='CONVERGING': old['phase']='SUPERSEDED_INCOMPLETE'
                s['history'].append(old)
            baseline={n:r['status']['committed'] for n,r in s['registry'].items()}
            s['fleet']=dict(id=secrets.token_hex(8),release=p['release'],canary=p.get('canary','a'),
                            mode='DEPLOY',phase='CANARY',baseline=baseline,canary_passed=False,
                            targets={n:'WAITING' for n in s['registry']},attempts=[])
            self.store.save(s); self.event('DEPLOY',fleet=s['fleet']['id'],release=p['release'])
        elif action=='pause':
            s['paused']=True
            if s['active'] and not s['active']['commit_authorized']: s['active']['cancel_requested']=True
            if s['fleet']: s['fleet']['phase']='PAUSED'
            self.store.save(s); self.event('PAUSE')
        elif action=='resume':
            require(s['active'] is None and s['fleet'] is not None,'Reconcile first')
            s['paused']=False
            f=s['fleet']; f['phase']='ROLLING_BACK' if f['mode']=='ROLLBACK' else ('ROLLING' if f['canary_passed'] else 'CANARY')
            for n,v in f['targets'].items():
                if v in ('FAILED','DEFERRED'): f['targets'][n]='WAITING'
            self.store.save(s); self.event('RESUME')
        elif action=='rollback':
            require(s['fleet'] is not None,'No fleet')
            s['fleet']['rollback_requested']=True; s['paused']=True; s['fleet']['phase']='PAUSED'
            if s['active'] and not s['active']['commit_authorized']: s['active']['cancel_requested']=True
            self.store.save(s); self.event('ROLLBACK_REQUEST')
            self.begin_rollback()
        else: raise ValueError('Unknown action')
        return self.store.read()

    def begin_rollback(self):
        s=self.store.read(); f=s['fleet']
        if f and f.get('rollback_requested') and s['active'] is None:
            f['rollback_requested']=False; f['mode']='ROLLBACK'; f['phase']='ROLLING_BACK'
            f['targets']={n:'WAITING' for n in s['registry']}; s['paused']=False
            self.store.save(s); self.event('ROLLBACK_BEGIN')

    def fresh(self,r):
        return r['seen_ns'] is not None and 0<=time.monotonic_ns()-r['seen_ns']<=self.freshness*1e9

    def poll(self,p):
        s=self.store.read(); node=p['node']; report=p['status']; r=s['registry'][node]
        require(report['node_uuid']==r['node_uuid'],'Node state was lost or replaced')
        boot=report['boot_sequence']; require(type(boot) is int and boot>=r['boot_sequence'],'Stale boot sequence')
        require(boot>r['boot_sequence'] or report['incarnation']==r['incarnation'],'Reused boot identity')
        changed=report['incarnation']!=r['incarnation']
        sequence=p['sequence']
        require(type(sequence) is int and sequence>0 and
                (boot>r['boot_sequence'] or sequence>r.get('poll_sequence',0)), 'Stale poll sequence')
        if boot==r['boot_sequence'] and r['status'] is not None:
            require(report['generation']>=r['status']['generation'] and report['revision']>=r['status']['revision'], 'Regressed node status')
        r['poll_sequence']=sequence
        r.update(boot_sequence=boot,incarnation=report['incarnation'],seen_ns=time.monotonic_ns(),status=report,
                 healthy=bool(p.get('probe') and p['probe'].get('result')==14 and
                              p['probe'].get('route')==report['route'] and
                              p['probe'].get('incarnation')==report['incarnation']))
        self.store.save(s)
        if changed:
            self.base('register',dict(node=node,incarnation=report['incarnation'],expected=s['agents'].get(node)))
            # A restarted node recovers its committed baseline; reconcile rather than
            # replaying a candidate using observations from a previous process.
            s=self.store.read()
            if s['active'] and s['active']['token']['node']==node:
                s['active']['needs_reconcile']=True; self.store.save(s)
        s=self.store.read(); a=s['active']
        if a and a['token']['node']==node:
            token=a['token']; match=report['token']==token
            if match and report['phase'] in ('COMMITTED','FAILED_RESTORED'):
                if report['phase']=='FAILED_RESTORED' and not r['healthy']:
                    # A journal label is not verified compensation. Keep the slot
                    # occupied through bad/missing data-plane evidence.
                    s['paused']=True; s['fleet']['phase']='PAUSED'
                    s['active']['restore_unverified']=True
                    self.store.save(s)
                    return {'command':'idle'}
                method='reconcile' if a['needs_reconcile'] or a['cancel_requested'] else 'finish'
                self.base(method,report)
                s=self.store.read(); f=s['fleet']
                committed=report['phase']=='COMMITTED'
                success=committed and r['healthy']
                f['targets'][node]='SUCCEEDED' if success else 'FAILED'
                f['attempts'].append(dict(node=node,token=token,result=report['phase'],serving_verified=r['healthy']))
                if success and node==f['canary'] and f['mode']=='DEPLOY':
                    f['canary_passed']=True; f['phase']='ROLLING'
                if not success or s['paused']: f['phase']='PAUSED'; s['paused']=True
                self.store.save(s)
                self.event('SETTLED',node=node,generation=token['generation'],result=report['phase'],release=report['route']['release'])
                self.begin_rollback()
                self.complete()
                return {'command':'idle'}
            args={'token':token,'incarnation':report['incarnation']}
            if a['needs_reconcile'] or a['cancel_requested']:
                # Commit authorization is durable. A restarted committed report is
                # reconciled above; an unfinished candidate must restore baseline.
                return {'command':'cancel' if match else 'refuse',**args}
            if not match:
                require(report['generation']<token['generation'],'Unexpected higher node generation')
                return {'command':'accept',**args}
            if report['phase']=='STAGED': return {'command':'activate',**args}
            require(report['phase']=='OBSERVING','Unexpected node phase')
            if a['binding'] is None:
                self.base('bind',report); a=self.store.read()['active']
            sample=p.get('sample')
            if sample and sample['challenge']==a['challenge']:
                try: self.base('sample',sample)
                except ValueError:
                    s=self.store.read(); s['paused']=True; s['active']['cancel_requested']=True
                    s['fleet']['phase']='PAUSED'; self.store.save(s); self.event('CANARY_REJECTED',node=node)
                    return {'command':'cancel',**args}
                a=self.store.read()['active']
            e=a['evidence']
            if e and e['count']>=self.samples and (e['finished_ns']-e['started_ns'])/1e9>=self.window:
                if time.monotonic_ns()-e['finished_ns']<=2_000_000_000:
                    return {'command':'commit',**args}
            if time.monotonic_ns()-a['challenge_ns']>2_000_000_000:
                # Expired evidence starts a fresh window; it never promotes.
                self.base('bind',report); a=self.store.read()['active']; e=None
            return {'command':'sample',**args,'challenge':a['challenge'],
                    'sequence':e['sequence']+1 if e else 1,'input':7}
        self.complete()
        s=self.store.read(); f=s['fleet']
        if not f or s['active'] or s['paused'] or f['phase'] in ('COMPLETED','ROLLED_BACK'): return {'command':'idle'}
        eligible=([f['canary']] if f['mode']=='DEPLOY' and not f['canary_passed'] else ['a','b','c'])
        for n in eligible:
            if f['targets'][n]=='SUCCEEDED': continue
            rr=s['registry'][n]
            if not self.fresh(rr):
                f['targets'][n]='DEFERRED'; f['phase']='CONVERGING'; continue
            # max-changing=1 is separate from min-other-observed-healthy=1.
            if not any(k!=n and self.fresh(v) and v['healthy'] for k,v in s['registry'].items()): continue
            if n!=node: continue
            release=f['release'] if f['mode']=='DEPLOY' else f['baseline'][n]
            self.store.save(s)
            planned=self.base('plan',dict(node=n,release=release,baseline=report['committed']))
            s=self.store.read(); s['fleet']['targets'][n]='ACTIVE'; self.store.save(s)
            token=planned['active']['token']; self.event('GRANT',node=n,release=release,generation=token['generation'],fleet=f['id'])
            return {'command':'accept','token':token,'incarnation':report['incarnation']}
        self.store.save(s)
        return {'command':'idle'}

    def complete(self):
        s=self.store.read(); f=s['fleet']
        if f and s['active'] is None and all(v=='SUCCEEDED' for v in f['targets'].values()):
            f['phase']='COMPLETED' if f['mode']=='DEPLOY' else 'ROLLED_BACK'
            self.store.save(s)
