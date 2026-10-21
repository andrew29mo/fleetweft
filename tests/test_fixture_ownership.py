import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from tools.mvp_ownership import Ownership, preflight, identity


class Host:
    def __init__(self):
        self.calls = []
        self.accounts = {}
        self.names = set()
        self.links = []
        self.loaded = set()
        self.ns_paths = {}
        self.enable_links = []

    def __call__(self, args, check=True):
        args = [str(a) for a in args]
        self.calls.append(args)
        rc, out = 0, ''
        if args[0] == 'getent':
            out = self.accounts.get(args[1], '')
            rc = 0 if out else 2
        elif args[:2] == ['systemctl', 'show']:
            if '-pMainPID' in args:
                out = 'MainPID=0\n'
            else:
                out = 'LoadState='+('loaded' if args[2] in self.loaded else 'not-found')+'\nFragmentPath=\nDropInPaths=\n'
        elif args[:3] == ['ip', 'netns', 'list']:
            out = '\n'.join(self.names)
        elif args[:4] == ['ip', '-j', 'link', 'show']:
            out = json.dumps(self.links)
        elif args[:3] == ['ip', 'netns', 'del']:
            self.names.remove(args[3])
            if args[3] in self.ns_paths:
                self.ns_paths[args[3]].unlink()
        elif args[:2] == ['systemctl', 'disable']:
            for path in self.enable_links:
                path.unlink()
        elif args[0] == 'userdel':
            del self.accounts['passwd']
        elif args[0] == 'groupdel':
            del self.accounts['group']
        return SimpleNamespace(returncode=rc, stdout=out, stderr='')


class FixtureOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base/'root'
        self.root.mkdir()
        (self.root/'owner').write_text('run-a')
        self.host = Host()
        self.state, self.conf, self.keys = [self.base/n for n in ('state', 'conf', 'keys')]
        self.system = self.base/'system'
        self.system.mkdir()
        self.ns = self.base/'netns'
        self.ns.mkdir()

    def preflight(self):
        return preflight(self.root, self.state, self.conf, self.keys, self.host,
                         uploaded=True, system_dirs=[self.system], netns=self.ns)

    def test_systemd_empty_pattern_status_one_is_absence(self):
        original=self.host
        def query(args,check=True):
            result=original(args,check=check)
            if args[:2]==['systemctl','list-unit-files']: result.returncode=1
            return result
        preflight(self.root,self.state,self.conf,self.keys,query,uploaded=True,system_dirs=[self.system],netns=self.ns)

    def test_template_is_checked_on_disk_not_as_instance(self):
        self.preflight()
        queries=[a for a in self.host.calls if a[:2]==['systemctl','show']]
        self.assertFalse(any(a[2]=='fleetweft-node@.service' for a in queries))
        (self.system/'fleetweft-node@.service').write_text('foreign unit')
        with self.assertRaisesRegex(RuntimeError,'Preexisting fixture'):
            self.preflight()

    def test_systemd_query_error_is_never_absence(self):
        original=self.host
        def query(args,check=True):
            result=original(args,check=check)
            if args[:2]==['systemctl','list-unit-files']:
                result.returncode=1; result.stderr='Failed to connect to bus'
            return result
        with self.assertRaisesRegex(RuntimeError,'enumerate'):
            preflight(self.root,self.state,self.conf,self.keys,query,uploaded=True,system_dirs=[self.system],netns=self.ns)

    def ledger(self, planned=()):
        ledger = Ownership(self.root, self.host, netns=self.ns)
        ledger.begin(planned)
        return ledger

    def no_mutations(self):
        self.assertFalse(any(c[0] in ('userdel', 'groupdel') or
                             c[:2] == ['systemctl', 'disable'] or
                             c[:3] == ['ip', 'netns', 'del'] for c in self.host.calls))

    def test_preexisting_account_and_group_preserved(self):
        for kind in ('passwd', 'group'):
            with self.subTest(kind=kind):
                self.host.accounts = {kind: 'foreign'}
                with self.assertRaises(RuntimeError):
                    self.preflight()
                self.assertFalse(self.state.exists())
                self.no_mutations()

    def test_all_preexisting_unit_and_dropin_paths_protected(self):
        for name in ('fleetweft-node@.service', 'fleetweft-fixture.service',
                     'fleetweft-node@a.service.d', 'fleetweft-controller.service.d'):
            with self.subTest(name=name):
                p = self.system/name
                p.write_text('foreign')
                with self.assertRaises(RuntimeError):
                    self.preflight()
                self.assertEqual(p.read_text(), 'foreign')
                p.unlink()
                self.no_mutations()

    def test_loaded_unit_namespace_and_link_protected(self):
        for field, value in (('loaded', {'fleetweft-node@a.service'}),
                             ('names', {'fw_ctl'}), ('links', [{'ifname': 'fwpa'}])):
            with self.subTest(resource=field):
                setattr(self.host, field, value)
                with self.assertRaises(RuntimeError):
                    self.preflight()
                setattr(self.host, field, [] if field == 'links' else set())
                self.no_mutations()

    def test_symlink_path_protected(self):
        self.keys.symlink_to(self.base/'missing')
        with self.assertRaises(RuntimeError):
            self.preflight()
        self.assertTrue(self.keys.is_symlink())

    def test_ordinary_owned_resources_cleanup(self):
        self.preflight()
        ledger = self.ledger([self.state, self.conf])
        ledger.mkdir(self.state)
        ledger.mkdir(self.conf)
        (self.state/'runtime.sqlite').write_text('mutable state')
        unit = self.system/'fleetweft-controller.service'
        ledger.write(unit, '[Service]\n')
        self.host.accounts = {'passwd': 'fleetweft:x:31:32::/:/usr/sbin/nologin',
                              'group': 'fleetweft:x:32:'}
        ledger.remember_account()
        result = ledger.cleanup(['fleetweft-controller.service'], lambda: 'firewall')
        self.assertTrue(all(result.values()))
        self.assertFalse(self.state.exists())
        self.assertFalse(unit.exists())
        self.assertFalse(self.host.accounts)
        self.assertFalse(ledger.path.exists())
        self.assertTrue((self.root/'owner').exists())

    def test_owned_namespace_removed_and_foreign_namespace_untouched(self):
        ledger = self.ledger()
        owned = self.ns/'fw_a'
        foreign = self.ns/'unrelated'
        owned.touch()
        foreign.touch()
        ledger.data['namespaces']['fw_a'] = dict(path=str(owned), identity=identity(owned))
        ledger.save()
        self.host.names = {'fw_a', 'unrelated'}
        self.host.ns_paths['fw_a'] = owned
        result = ledger.cleanup([], lambda: 'rules')
        self.assertTrue(result['namespaces_removed'])
        self.assertFalse(owned.exists())
        self.assertTrue(foreign.exists())
        self.assertEqual(self.host.names, {'unrelated'})

    def test_enablement_link_verified_and_removed(self):
        ledger = self.ledger()
        unit = self.system/'fleetweft-controller.service'
        ledger.write(unit, '[Service]\n')
        wants = self.system/'multi-user.target.wants'
        wants.mkdir()
        link = wants/unit.name
        link.symlink_to(unit)
        ledger.remember_link(link)
        self.host.enable_links.append(link)
        ledger.cleanup([unit.name], lambda: 'rules')
        self.assertFalse(link.is_symlink())

    def test_foreign_enablement_link_preserved(self):
        ledger = self.ledger()
        link = self.system/'fleetweft-controller.service'
        link.symlink_to('/ours')
        ledger.remember_link(link)
        link.unlink()
        link.symlink_to('/foreign')
        with self.assertRaisesRegex(RuntimeError, 'Enablement ownership changed'):
            ledger.cleanup([], lambda: 'rules')
        self.assertEqual(str(link.readlink()), '/foreign')
        self.no_mutations()

    def test_missing_manifest_cannot_claim_cleanup(self):
        with self.assertRaises(FileNotFoundError):
            Ownership(self.root, self.host).cleanup([], lambda: 'rules')
        self.no_mutations()

    def test_changed_or_foreign_owner_refuses_before_mutations(self):
        ledger = self.ledger()
        unit = self.system/'fleetweft-controller.service'
        ledger.write(unit, 'ours')
        unit.write_text('foreign')
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            ledger.cleanup(['fleetweft-controller.service'], lambda: 'rules')
        self.assertEqual(unit.read_text(), 'foreign')
        self.no_mutations()
        unit.write_text('ours')
        (self.root/'owner').write_text('run-b')
        with self.assertRaisesRegex(RuntimeError, 'Foreign'):
            Ownership(self.root, self.host).cleanup([], lambda: 'rules')
        self.no_mutations()

    def test_partial_unrecorded_account_or_namespace_refuses_cleanup(self):
        ledger = self.ledger()
        for attr, value in (('accounts', {'passwd': 'foreign'}), ('names', {'fw_ctl'})):
            with self.subTest(resource=attr):
                setattr(self.host, attr, value)
                with self.assertRaisesRegex(RuntimeError, 'Unrecorded'):
                    ledger.cleanup([], lambda: 'rules')
                setattr(self.host, attr, {} if attr == 'accounts' else set())
                self.no_mutations()

    def test_created_but_unrecorded_path_never_adopted(self):
        ledger = self.ledger([self.state])
        self.state.mkdir()
        (self.state/'foreign').write_text('keep')
        with self.assertRaisesRegex(RuntimeError, 'Unrecorded'):
            ledger.cleanup([], lambda: 'rules')
        self.assertTrue((self.state/'foreign').exists())
        self.no_mutations()

    def test_namespace_filesystem_collision_is_never_adopted(self):
        ledger=self.ledger()
        (self.ns/'fw_a').write_text('foreign namespace mount placeholder')
        with self.assertRaisesRegex(RuntimeError,'refusing adoption'):
            ledger.start_topology('boot-new')
        self.assertTrue((self.ns/'fw_a').exists())
        self.no_mutations()

    def test_reboot_allows_absent_names_only(self):
        ledger = self.ledger()
        ledger.start_topology('boot-one')
        with self.assertRaisesRegex(RuntimeError, 'already attempted'):
            ledger.start_topology('boot-one')
        ledger.start_topology('boot-two')
        self.assertEqual(ledger.data['topology_boot'], 'boot-two')
        self.host.names.add('fw_a')
        with self.assertRaisesRegex(RuntimeError, 'refusing adoption'):
            ledger.start_topology('boot-three')
        self.no_mutations()

    def test_changed_namespace_inode_preserved(self):
        ledger = self.ledger()
        ns = self.ns/'fw_a'
        ns.touch()
        ledger.data['namespaces']['fw_a'] = dict(path=str(ns), identity=[-1, -1])
        ledger.save()
        with self.assertRaisesRegex(RuntimeError, 'Namespace ownership changed'):
            ledger.cleanup([], lambda: 'rules')
        self.assertTrue(ns.exists())
        self.no_mutations()

    def test_firewall_change_does_not_claim_cleanup_success(self):
        ledger = self.ledger()
        observations = iter(('before', 'after'))
        with self.assertRaisesRegex(RuntimeError, 'ruleset changed during cleanup'):
            ledger.cleanup([], lambda: next(observations))
        self.assertTrue(ledger.path.exists())


if __name__ == '__main__':
    unittest.main()
