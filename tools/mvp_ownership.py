"""Fail-closed ownership ledger for the disposable Linux VM fixture.

The ledger is kept in the uploaded run root, outside mutable service state. No
resource is adopted merely because it has the fixture's conventional name.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess

NAMES = ('fw_ctl', 'fw_a', 'fw_b', 'fw_c')
LINKS = tuple('fw'+side+n for n in 'abc' for side in ('p', 'n'))
UNITS = ('fleetweft-controller.service', 'fleetweft-node@.service',
         'fleetweft-fixture.service', 'fleetweft-fixture-proxy.service', *(f'fleetweft-node@{n}.service' for n in 'abc'))


def execute(args, check=True):
    p = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=20)
    if check and p.returncode:
        raise RuntimeError('Ownership probe/action failed: '+str(args))
    return p


def exists(path):
    return path.exists() or path.is_symlink()


def account(kind, run):
    p = run(['getent', kind, 'fleetweft'], check=False)
    if p.returncode == 2:
        return None
    if p.returncode != 0 or not p.stdout.strip():
        raise RuntimeError('Cannot establish '+kind+' ownership')
    return p.stdout.strip()


def preflight(root=Path('/opt/fleetweft'), state=Path('/var/lib/fleetweft'),
              conf=Path('/etc/fleetweft'), keys=Path('/root/fleetweft-fixture'),
              run=execute, uploaded=False, system_dirs=None, netns=Path('/run/netns')):
    paths = [state, conf, keys]
    if not uploaded:
        paths.append(root)
    if any(exists(p) for p in paths):
        raise RuntimeError('Preexisting fixture path')
    if account('passwd', run) or account('group', run):
        raise RuntimeError('Preexisting fleetweft account/group')
    directories = system_dirs if system_dirs is not None else [Path(p) for p in
        ('/etc/systemd/system', '/run/systemd/system', '/usr/local/lib/systemd/system',
         '/usr/lib/systemd/system', '/lib/systemd/system')]
    for directory in directories:
        for candidate in directory.rglob('*'):
            if candidate.name in UNITS or candidate.name in {u+'.d' for u in UNITS}:
                raise RuntimeError('Preexisting fixture systemd path: '+str(candidate))
        for unit in UNITS:
            if exists(directory/unit) or exists(directory/(unit+'.d')):
                raise RuntimeError('Preexisting fixture unit/drop-in: '+str(directory/unit))
    # Includes generated/transient units and enablement aliases outside the
    # conventional top-level unit locations.
    p = run(['systemctl', 'list-unit-files', '--no-legend', '--no-pager', 'fleetweft*'], check=False)
    # systemd 255 returns 1 with no output when a pattern has no matches.
    # D-Bus/permission/execution errors are not absence evidence.
    if p.returncode != 0 and not (p.returncode == 1 and not p.stdout.strip() and not p.stderr.strip()):
        raise RuntimeError('Cannot enumerate fixture systemd units')
    if any(line.split()[0] in UNITS for line in p.stdout.splitlines() if line.split()):
        raise RuntimeError('Preexisting fixture systemd unit')
    for unit in UNITS:
        if '@.' in unit: continue  # Templates are checked as files/list entries; only instances have properties.
        p = run(['systemctl', 'show', unit, '-pLoadState', '-pFragmentPath', '-pDropInPaths'])
        values = dict(line.split('=', 1) for line in p.stdout.splitlines() if '=' in line)
        if values.get('LoadState') != 'not-found' or values.get('FragmentPath') or values.get('DropInPaths'):
            raise RuntimeError('Preexisting or unknown fixture systemd state: '+unit)
    names = {line.split()[0] for line in run(['ip', 'netns', 'list']).stdout.splitlines() if line.split()}
    if names.intersection(NAMES) or any(exists(netns/n) for n in NAMES):
        raise RuntimeError('Preexisting fixture namespace')
    links = json.loads(run(['ip', '-j', 'link', 'show']).stdout)
    if any(link['ifname'] in LINKS for link in links):
        raise RuntimeError('Preexisting fixture interface')


def identity(path):
    s = path.lstat()
    if stat.S_ISLNK(s.st_mode):
        raise RuntimeError('Refusing symlink resource: '+str(path))
    return [s.st_dev, s.st_ino]


class Ownership:
    def __init__(self, root, run=execute, netns=Path('/run/netns')):
        self.root = Path(root)
        self.run = run
        self.netns = Path(netns)
        self.path = self.root/'fixture-ownership.json'
        self.owner = (self.root/'owner').read_text().strip()
        if not self.owner:
            raise RuntimeError('Missing run owner')
        self.data = None

    def begin(self, planned=()):
        data = dict(version=1, root=str(self.root.resolve()), owner=self.owner,
                    root_identity=identity(self.root), planned=[str(p) for p in planned], paths={}, account=None, namespaces={}, links={}, topology_boot=None)
        with self.path.open('x') as stream:
            json.dump(data, stream)
        self.data = data

    def load(self):
        if self.path.is_symlink():
            raise RuntimeError('Symlink ownership ledger')
        data = json.loads(self.path.read_text())
        if (data.get('version') != 1 or data.get('root') != str(self.root.resolve()) or
                data.get('owner') != self.owner or data.get('root_identity') != identity(self.root)):
            raise RuntimeError('Foreign ownership ledger')
        self.data = data
        return self

    def save(self):
        tmp = self.path.with_suffix('.tmp')
        with tmp.open('x') as stream:
            json.dump(self.data, stream)
        tmp.replace(self.path)

    def remember(self, path, directory=False):
        path = Path(path)
        record = dict(identity=identity(path), directory=directory)
        if not directory:
            record['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.data['paths'][str(path)] = record
        self.save()

    def mkdir(self, path, mode=0o755):
        Path(path).mkdir(mode=mode)
        self.remember(path, directory=True)

    def write(self, path, content):
        with Path(path).open('x') as stream:
            stream.write(content)
        self.remember(path)

    def remember_link(self, path):
        path = Path(path)
        if not path.is_symlink():
            raise RuntimeError('Expected owned enablement symlink: '+str(path))
        st = path.lstat()
        self.data['paths'][str(path)] = dict(identity=[st.st_dev, st.st_ino], directory=False, target=os.readlink(path))
        self.save()

    def remember_account(self):
        self.data['account'] = dict(passwd=account('passwd', self.run), group=account('group', self.run))
        if not all(self.data['account'].values()):
            raise RuntimeError('Created account/group is missing')
        self.save()

    def validate(self):
        for name in self.data['planned']:
            if exists(Path(name)) and name not in self.data['paths']:
                raise RuntimeError('Unrecorded resource: '+name)
        for unit in UNITS:
            if '@.' in unit: continue
            probe = self.run(['systemctl', 'show', unit, '-pLoadState', '-pFragmentPath', '-pDropInPaths'])
            values = dict(line.split('=', 1) for line in probe.stdout.splitlines() if '=' in line)
            fragment = values.get('FragmentPath', '')
            drops = values.get('DropInPaths', '').split()
            for resource in ([fragment] if fragment else []) + drops:
                path = Path(resource)
                if resource not in self.data['paths'] and not (path.name == 'checkpoint.conf' and str(path.parent) in self.data['paths']):
                    raise RuntimeError('Foreign loaded systemd resource: '+resource)
            if values.get('LoadState') not in ('not-found', 'loaded') or (values.get('LoadState') == 'loaded' and not fragment):
                raise RuntimeError('Unknown loaded systemd ownership: '+unit)
        current_names = {line.split()[0] for line in self.run(['ip', 'netns', 'list']).stdout.splitlines() if line.split()}
        if current_names.intersection(NAMES) - self.data['namespaces'].keys():
            raise RuntimeError('Unrecorded fixture namespace')
        for name, record in self.data['paths'].items():
            path = Path(name)
            if not exists(path):
                raise RuntimeError('Owned resource disappeared: '+name)
            if 'target' in record:
                st = path.lstat()
                if not path.is_symlink() or [st.st_dev, st.st_ino] != record['identity'] or os.readlink(path) != record['target']:
                    raise RuntimeError('Enablement ownership changed: '+name)
                continue
            if identity(path) != record['identity']:
                raise RuntimeError('Resource ownership changed: '+name)
            if not record['directory'] and hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
                raise RuntimeError('Owned file changed: '+name)
            if record['directory'] and name.endswith('.service.d'):
                for child in path.iterdir():
                    if str(child) in self.data['paths']:
                        continue
                    # Only the explicit fixture scenario checkpoint settings are mutable.
                    if (child.name != 'checkpoint.conf' or child.is_symlink() or
                        child.read_text() not in ('[Service]\nEnvironment=FLEETWEFT_CHECKPOINT=staged\n',
                                                  '[Service]\nEnvironment=FLEETWEFT_CHECKPOINT=after_route\n',
                                                  '[Service]\nEnvironment=FLEETWEFT_CHECKPOINT=after_commit\n',
                                                  '[Service]\nEnvironment=FLEETWEFT_CHECKPOINT=after_cancel\n')):
                        raise RuntimeError('Foreign systemd drop-in: '+str(child))
        if not self.data['account'] and (account('passwd', self.run) or account('group', self.run)):
            raise RuntimeError('Unrecorded fixture account/group')
        if self.data['account']:
            current = dict(passwd=account('passwd', self.run), group=account('group', self.run))
            if current != self.data['account']:
                raise RuntimeError('Account ownership changed')
        for name, record in self.data['namespaces'].items():
            path = Path(record['path'])
            if not exists(path) or identity(path) != record['identity']:
                raise RuntimeError('Namespace ownership changed: '+name)
        self.check_links()

    def check_links(self):
        links = json.loads(self.run(['ip', '-j', 'link', 'show']).stdout)
        for link in links:
            if link['ifname'] in LINKS:
                record = self.data['links'].get(link['ifname'])
                if not record or link['ifindex'] != record['ifindex'] or link.get('ifalias') != self.owner:
                    raise RuntimeError('Interface ownership changed: '+link['ifname'])

    def start_topology(self, boot):
        self.load()
        # /run/netns is volatile. A new boot may recreate only absent names.
        if self.data['topology_boot'] == boot:
            raise RuntimeError('Topology already attempted this boot')
        names = {line.split()[0] for line in self.run(['ip', 'netns', 'list']).stdout.splitlines() if line.split()}
        if names.intersection(NAMES) or any(exists(self.netns/n) for n in NAMES):
            raise RuntimeError('Namespace already exists; refusing adoption')
        old_namespaces = self.data['namespaces']
        self.data['namespaces'] = {}
        try:
            self.validate()
        except BaseException:
            self.data['namespaces'] = old_namespaces
            raise
        self.data.update(namespaces={}, links={}, topology_boot=boot)
        self.save()

    def add_namespace(self, name):
        self.run(['ip', 'netns', 'add', name])
        path = self.netns/name
        self.data['namespaces'][name] = dict(path=str(path), identity=identity(path))
        self.save()

    def add_veth(self, left, right):
        self.run(['ip', 'link', 'add', left, 'type', 'veth', 'peer', 'name', right])
        for name in (left, right):
            self.run(['ip', 'link', 'set', 'dev', name, 'alias', self.owner])
            link = json.loads(self.run(['ip', '-j', 'link', 'show', 'dev', name]).stdout)[0]
            self.data['links'][name] = dict(ifindex=link['ifindex'])
            self.save()

    def cleanup(self, units, firewall):
        self.load()
        self.validate()  # Validate every resource before the first destructive action.
        before_firewall = firewall()
        paths = self.data['paths']
        owned_units = [u for u in units if any(Path(p).name in (u, u+'.d') for p in paths)]
        if owned_units:
            self.run(['systemctl', 'disable', '--now', *owned_units])
            for unit in owned_units:
                p = self.run(['systemctl', 'show', unit, '-pMainPID'])
                if p.stdout.strip() != 'MainPID=0':
                    raise RuntimeError('Owned unit still running: '+unit)
        # disable removes enablement symlinks; their identity was checked before
        # invoking systemctl and they must now be absent.
        for name, record in list(paths.items()):
            if 'target' in record:
                if exists(Path(name)):
                    raise RuntimeError('Enablement link remains after disable: '+name)
                del paths[name]
        self.save()
        self.validate()
        for name in self.data['namespaces']:
            self.run(['ip', 'netns', 'del', name])
        # A failed topology can leave a veth in the host namespace.
        links = json.loads(self.run(['ip', '-j', 'link', 'show']).stdout)
        for link in links:
            if link['ifname'] in self.data['links']:
                present = json.loads(self.run(['ip', '-j', 'link', 'show']).stdout)
                if any(row['ifname'] == link['ifname'] for row in present):
                    self.run(['ip', 'link', 'del', link['ifname']])
        if self.data['account']:
            self.run(['userdel', 'fleetweft'])
            if account('passwd', self.run) is not None:
                raise RuntimeError('Owned account remains')
            group = account('group', self.run)
            if group is not None:
                if group != self.data['account']['group']:
                    raise RuntimeError('Group ownership changed')
                self.run(['groupdel', 'fleetweft'])
            if account('group', self.run) is not None:
                raise RuntimeError('Owned group remains')
        for name in sorted(paths, key=lambda p: len(Path(p).parts), reverse=True):
            path = Path(name)
            if paths[name]['directory']:
                shutil.rmtree(path)
            else:
                path.unlink()
        self.run(['systemctl', 'daemon-reload'])
        if any(exists(Path(r['path'])) for r in self.data['namespaces'].values()):
            raise RuntimeError('Owned namespace remains')
        if firewall() != before_firewall:
            raise RuntimeError('Unrelated root ruleset changed during cleanup')
        self.path.unlink()
        return dict(units_stopped=True, namespaces_removed=True, root_firewall_unchanged=True, credentials_removed=True)
