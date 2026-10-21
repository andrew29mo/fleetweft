"""Single route writer and conservative recovery of a fixed application backend."""
import hashlib
import os
from pathlib import Path
import secrets
import selectors
import signal
import subprocess
import sys
import threading
import time
import json
from urllib.parse import urlencode
from urllib.error import HTTPError
from .net import request
from .store import Store, require


def recipe_digest(release):
    return hashlib.sha256(Path(__file__).with_name('worker.py').read_bytes() + release.encode()).hexdigest()


def identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        if fields[0] == 'Z': return None
        return {'pid': pid, 'start': int(fields[19]),
                'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except (FileNotFoundError, ProcessLookupError): return None


WORKER_START_TIMEOUT = 3

class Node:
    def __init__(self, root, name, controller, artifacts=None, tls=None, secure=False):
        self.artifacts, self.tls = artifacts, tls
        if secure:
            require((Path(root)/'state.sqlite').is_file(), 'Explicit node provisioning required')
        self.name = name
        self.controller = controller
        self.store = Store(root, {'committed': 'v1', 'generation': 0, 'accepted': None,
                                  'phase': 'IDLE', 'children': [], 'revision': 0})
        self.lock = threading.RLock(); self.children = []; self.route = None
        self.routes = threading.Condition(); self.inflight = {}
        self.incarnation = secrets.token_hex(16)
        s = self.store.read()
        if secure:
            require(s.get('node_uuid') and type(s.get('boot_sequence')) is int, 'Invalid node identity')
            s['boot_sequence'] += 1
            self.store.save(s)
        # The state is local and trusted; no PID signaling based on PID alone.
        for i in s['children']:
            if identity(i['pid']) == i:
                fd = os.pidfd_open(i['pid'])
                try:
                    if identity(i['pid']) == i: signal.pidfd_send_signal(fd, signal.SIGKILL)
                    poll = selectors.DefaultSelector(); poll.register(fd, selectors.EVENT_READ)
                    try: require(bool(poll.select(2)), 'Old worker retirement not observed')
                    finally: poll.close()
                finally: os.close(fd)
        s['children'] = []
        if s['accepted'] and s['phase'] != 'COMMITTED': s['phase'] = 'FAILED_RESTORED'
        self.store.save(s)
        self.route = self.spawn(s['committed'])
        s = self.store.read(); s['revision'] += 1; self.store.save(s)

    def checkpoint(self, name):
        # Test barrier only: it delays the unchanged runtime at a named boundary.
        # It grants no alternate switch path and is unset in normal execution.
        if os.environ.get('FLEETWEFT_CHECKPOINT') != name: return
        p = self.store.root / 'checkpoint'; p.write_text(name)
        limit = time.monotonic() + 15
        while not (self.store.root / 'release-checkpoint').exists():
            require(time.monotonic() < limit, 'Checkpoint timeout')
            time.sleep(.01)

    def spawn(self, release):
        instance = secrets.token_hex(16)
        command = ([sys.executable, '-I', str(self.artifacts.path(release)), release, instance]
                   if self.artifacts else [sys.executable, '-I', '-m', 'fleetweft.worker', release, instance])
        p = subprocess.Popen(command,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                             env={**os.environ, 'FLEETWEFT_NODE': self.name})
        self.children.append(p)
        try:
            i = identity(p.pid); require(i is not None, 'Worker exited')
            s = self.store.read(); s['children'].append(i); self.store.save(s)
            # A byte of stdout is not a complete readiness message. Bound both
            # time and size; readline() after select() can otherwise block forever.
            ready = b''; deadline = time.monotonic() + WORKER_START_TIMEOUT
            os.set_blocking(p.stdout.fileno(), False)
            with selectors.DefaultSelector() as sel:
                sel.register(p.stdout, selectors.EVENT_READ)
                while b'\n' not in ready:
                    require(time.monotonic() < deadline and len(ready) <= 1024, 'Worker startup timeout/size')
                    require(bool(sel.select(max(0, deadline-time.monotonic()))), 'Worker startup timeout')
                    chunk = os.read(p.stdout.fileno(), 1025-len(ready))
                    require(bool(chunk), 'Worker exited before readiness'); ready += chunk
            port = json.loads(ready.split(b'\n',1)[0])['port']
            require(type(port) is int and 0 < port < 65536 and p.poll() is None, 'Invalid worker readiness')
            return {'release': release, 'worker': instance, 'port': port,
                    'digest': self.artifacts.catalog[release] if self.artifacts else recipe_digest(release)}
        except BaseException:
            if p.poll() is None: p.kill()
            p.wait(timeout=3); p.stdout.close(); self.children.remove(p)
            s = self.store.read()
            s['children'] = [i for child in self.children if (i := identity(child.pid)) is not None]
            self.store.save(s)
            raise

    def snapshot(self):
        s = self.store.read()
        return {'token': s['accepted'], 'incarnation': self.incarnation, 'phase': s['phase'],
                'route': self.route, 'generation': s['generation'], 'revision': s['revision'],
                'committed': s['committed'], 'workers': s['children'],
                'node_uuid': s.get('node_uuid'), 'boot_sequence': s.get('boot_sequence')}

    def switch(self, route):
        with self.routes:
            self.route = route

    def retire_obsolete(self):
        """Keep the committed worker; let previously pinned requests finish first.

        A bounded drain may interrupt stalled requests. Failure is propagated,
        never treated as proof that the old process has exited.
        """
        keep = self.route['worker']
        for child in list(self.children):
            worker = child.args[-1]
            if worker == keep: continue
            deadline = time.monotonic() + 2.5
            with self.routes:
                while self.inflight.get(worker, 0) and time.monotonic() < deadline:
                    self.routes.wait(max(0, deadline-time.monotonic()))
            if child.poll() is None: child.kill()
            child.wait(timeout=3); child.stdout.close(); self.children.remove(child)
        s = self.store.read()
        s['children'] = [i for p in self.children if (i := identity(p.pid)) is not None]
        self.store.save(s)

    def work(self, x, challenge, delay_ms=0):
        with self.routes:
            route = self.route  # Borrow and switch share the same lock.
            require(route is not None, 'No route')
            worker = route['worker']; self.inflight[worker] = self.inflight.get(worker,0)+1
        try:
            result = request('http://127.0.0.1:' + str(route['port']),
                             '/work?' + urlencode({'x': x, 'challenge': challenge,'delay_ms':delay_ms}))
            require(result['worker'] == worker and result['release'] == route['release'], 'Wrong worker')
            return {**result, 'route': route, 'incarnation': self.incarnation}
        finally:
            with self.routes:
                self.inflight[worker] -= 1; self.routes.notify_all()
                if not self.inflight[worker]: del self.inflight[worker]

    def call(self, action, p):
        with self.lock:
            if action == 'status': return self.snapshot()
            s = self.store.read()
            token = p['token']
            require(token['node'] == self.name, 'Wrong node')
            require(p['incarnation'] == self.incarnation, 'Stale incarnation')
            if action == 'refuse':
                require(s['phase'] in ('IDLE','COMMITTED','FAILED_RESTORED') and token['generation'] > s['generation'], 'Cannot fence grant')
                require(token['baseline']==s['committed'], 'Baseline mismatch')
                s.update(accepted=token,generation=token['generation'],phase='FAILED_RESTORED')
                self.store.save(s)
                return self.snapshot()
            if action == 'accept':
                if s['accepted'] == token: return self.snapshot()
                require(s['phase'] in ('IDLE', 'COMMITTED', 'FAILED_RESTORED'), 'Existing unsettled operation')
                require(type(token['generation']) is int and token['generation'] > s['generation'], 'Stale grant')
                require(token['baseline'] == s['committed'], 'Baseline mismatch')
                require(token['digest'] == (self.artifacts.catalog[token['release']] if self.artifacts else recipe_digest(token['release'])), 'Wrong digest')
                s.update(accepted=token, generation=token['generation'], phase='STAGED')
                self.store.save(s); self.checkpoint('staged')
            else:
                require(s['accepted'] == token and p['incarnation'] == self.incarnation, 'Stale executor')
                if action == 'activate':
                    require(s['phase'] == 'STAGED', 'Not staged')
                    candidate = self.spawn(token['release']); s = self.store.read()
                    s['phase'] = 'ACTIVATING'; self.store.save(s)
                    self.checkpoint('before_route')
                    self.switch(candidate)
                    self.checkpoint('after_route')
                    s['phase'] = 'OBSERVING'; s['revision'] += 1; self.store.save(s)
                elif action == 'sample':
                    require(s['phase'] == 'OBSERVING', 'Not observing')
                    result = self.work(p['input'], p['challenge'])
                    require(result['route'] == self.route, 'Route changed')
                    # The caller/Controller checks business result independently.
                    return {**self.snapshot(), 'sequence': p['sequence'], 'challenge': result['challenge'],
                            'input': p['input'], 'result': result['result']}
                elif action == 'commit':
                    require(s['phase'] == 'OBSERVING', 'Not observing')
                    require(self.route['digest'] == token['digest'], 'Wrong live digest')
                    try:approval=(self.tls.request if self.tls else request)(self.controller, '/authorize_commit', self.snapshot())
                    except HTTPError as exc:
                        if exc.code==409:raise ValueError('Controller refused commit') from None
                        raise
                    require(approval['active']['token']==token and approval['active']['commit_authorized'], 'Commit not authorized')
                    self.checkpoint('before_commit')
                    s.update(committed=token['release'], phase='COMMITTED')
                    self.store.save(s); self.checkpoint('after_commit')
                    self.retire_obsolete()
                elif action == 'cancel':
                    require(s['phase'] in ('STAGED', 'ACTIVATING', 'OBSERVING'), 'Cannot cancel committed operation')
                    self.switch(self.spawn(s['committed'])); s = self.store.read()
                    s['phase'] = 'FAILED_RESTORED'; s['revision'] += 1; self.store.save(s)
                    self.checkpoint('after_cancel')
                    self.retire_obsolete()
                else: raise ValueError('Unknown action')
            return self.snapshot()

    def close(self):
        for p in self.children:
            if p.poll() is None: p.kill()
            p.wait(timeout=3)
            p.stdout.close()
        self.store.close()
