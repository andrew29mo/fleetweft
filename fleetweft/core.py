"""Durable grant ownership and canary evidence, shared by service and tests."""
import secrets
import threading
import time
from .store import Store, require
from .node import recipe_digest


class Controller:
    def __init__(self, root, samples=3, window=.05):
        self.store = Store(root, {'generation': 0, 'epoch': 0, 'active': None,
                                  'paused': False, 'agents': {}, 'last': None})
        self.lock = threading.RLock()
        self.samples, self.window = samples, window
        s = self.store.read(); s['epoch'] += 1
        if s['active']:
            s['active']['needs_reconcile'] = True
            s['active']['binding'] = None
            s['active']['evidence'] = None
        self.store.save(s)

    def call(self, action, p):
        with self.lock:
            s = self.store.read()
            if action == 'status':
                return {**s, 'quiesced': s['active'] is None}
            if action == 'plan':
                require(s['active'] is None and not s['paused'], 'Occupied or paused')
                require(p['node'] in s['agents'], 'Unregistered node')
                require(p['release'] in ('v1', 'v2', 'v3', 'bad'), 'Unknown fixture release')
                s['generation'] += 1
                token = {'epoch': s['epoch'], 'generation': s['generation'],
                         'node': p['node'], 'op': secrets.token_hex(16), 'release': p['release'],
                         'baseline': p['baseline'], 'digest': recipe_digest(p['release'])}
                s['active'] = {'token': token, 'binding': None, 'evidence': None,
                               'challenge': secrets.token_hex(16), 'cancel_requested': False,
                               'challenge_ns': time.monotonic_ns(),
                               'needs_reconcile': False, 'commit_authorized': False}
            elif action == 'grant':
                require(s['active'] and s['active']['token']['node'] == p['node'], 'No grant')
                # Same durable capability on retry, even when pause stops new grants.
                return s['active']['token']
            elif action == 'pause':
                s['paused'] = True
            elif action == 'resume':
                require(s['active'] is None, 'Unsettled operation')
                s['paused'] = False
            elif action == 'register':
                old = s['agents'].get(p['node'])
                require(p.get('expected') == old, 'Registration conflict')
                s['agents'][p['node']] = p['incarnation']
                if old != p['incarnation'] and s['active'] and s['active']['token']['node'] == p['node']:
                    s['active']['binding'] = None; s['active']['evidence'] = None
                    s['active']['challenge'] = secrets.token_hex(16)
                    s['active']['challenge_ns'] = time.monotonic_ns()
            elif action == 'cancel':
                require(s['active'] is not None, 'No operation')
                s['active']['cancel_requested'] = True
                s['paused'] = True
            elif action in ('bind', 'sample', 'authorize_commit', 'finish', 'reconcile'):
                if action in ('finish', 'reconcile') and s['active'] is None and p == s['last']:
                    return {**s, 'quiesced': True}
                a = s['active']; require(a is not None and p['token'] == a['token'], 'Stale operation')
                require(p['incarnation'] == s['agents'].get(a['token']['node']), 'Stale incarnation')
                if action == 'bind':
                    require(not a['needs_reconcile'], 'Reconcile required')
                    require(not a['cancel_requested'], 'Cancellation pending')
                    require(p['route']['release'] == a['token']['release'], 'Wrong release')
                    require(p['route']['digest'] == a['token']['digest'], 'Wrong digest')
                    a['binding'] = p['route']; a['evidence'] = None
                    a['challenge'] = secrets.token_hex(16)
                    a['challenge_ns'] = time.monotonic_ns()
                elif action == 'sample':
                    require(not a['needs_reconcile'] and not a['cancel_requested'], 'Not observing')
                    require(a['binding'] is not None and p['route'] == a['binding'], 'Stale route')
                    require(p['challenge'] == a['challenge'] and p['result'] == p['input'] * 2, 'Bad canary')
                    old = a['evidence']; require(p['sequence'] == (old['sequence'] + 1 if old else 1), 'Stale sample')
                    now = time.monotonic_ns()
                    require(0 <= now - a['challenge_ns'] <= 2_000_000_000, 'Expired sample challenge')
                    a['evidence'] = {'sequence': p['sequence'], 'count': old['count'] + 1 if old else 1,
                                     'started_ns': old['started_ns'] if old else now, 'finished_ns': now}
                    a['challenge'] = secrets.token_hex(16)
                    a['challenge_ns'] = now
                elif action == 'authorize_commit':
                    require(not a['needs_reconcile'] and not a['cancel_requested'] and not s['paused'], 'Not promotable')
                    require(p['phase']=='OBSERVING' and p['route']==a['binding'], 'Wrong live candidate')
                    e=a['evidence'];require(e is not None and e['count']>=self.samples, 'Insufficient samples')
                    require((e['finished_ns']-e['started_ns'])/1e9>=self.window, 'Observation too short')
                    require(0<=time.monotonic_ns()-e['finished_ns']<=2_000_000_000, 'Stale observation')
                    a['commit_authorized']=True
                else:
                    require(p['phase'] in ('COMMITTED', 'FAILED_RESTORED'), 'Unknown execution result')
                    if p['phase'] == 'COMMITTED':
                        require(a['commit_authorized'], 'Commit was not authorized')
                        require(p['route']['release'] == a['token']['release'], 'Wrong committed route')
                        require(p['route']['digest'] == a['token']['digest'], 'Wrong committed digest')
                        if action == 'finish':
                            require(not a['needs_reconcile'] and not a['cancel_requested'], 'Not promotable')
                            e = a['evidence']; require(e is not None and e['count'] >= self.samples, 'Insufficient samples')
                            require((e['finished_ns'] - e['started_ns']) / 1e9 >= self.window, 'Observation too short')
                            require(p['route'] == a['binding'], 'Route changed')
                    else:
                        require(p['route']['release'] == a['token']['baseline'], 'Not restored')
                    # Reconciliation settles a durable local result, never reuses
                    # old health evidence to promote the next cohort automatically.
                    s['last'] = p
                    s['active'] = None
                    if action == 'reconcile' or p['phase'] != 'COMMITTED': s['paused'] = True
            else:
                raise ValueError('Unknown action')
            self.store.save(s)
            return {**s, 'quiesced': s['active'] is None}
