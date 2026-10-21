import tempfile
import unittest
from unittest.mock import patch
from fleetweft.core import Controller
from fleetweft.node import recipe_digest


class Contracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.c = Controller(self.tmp.name, 2, 0)
        self.c.call('register', {'node': 'a', 'incarnation': 'boot-a', 'expected': None})
        self.c.call('plan', {'node': 'a', 'release': 'v2', 'baseline': 'v1'})
        self.t = self.c.call('grant', {'node': 'a'})
        self.route = {'release': 'v2', 'digest': recipe_digest('v2'), 'worker': 'worker-a', 'port': 9}
        self.payload = {'token': self.t, 'incarnation': 'boot-a', 'route': self.route}
    def tearDown(self): self.c.store.close(); self.tmp.cleanup()
    def sample(self, seq):
        a = self.c.call('status', {})['active']
        return {**self.payload, 'sequence': seq, 'challenge': a['challenge'], 'input': 7, 'result': 14}
    def test_retry_has_same_capability(self):
        self.assertEqual(self.t, self.c.call('grant', {'node': 'a'}))
    def test_pause_keeps_unknown_occupancy(self):
        s = self.c.call('pause', {}); self.assertFalse(s['quiesced'])
        self.assertIsNotNone(s['active'])
        self.assertEqual(s['active']['token'], self.t)
        with self.assertRaises(ValueError): self.c.call('plan', {'node': 'a', 'release': 'v3'})
        with self.assertRaises(ValueError): self.c.call('resume', {})
    def test_cancel_requires_target_confirmation(self):
        self.c.call('cancel', {}); self.assertFalse(self.c.call('status', {})['quiesced'])
        p = {**self.payload, 'phase': 'FAILED_RESTORED', 'route': {'release': 'v1'}}
        self.assertTrue(self.c.call('finish', p)['quiesced'])
    def test_cancel_does_not_accept_false_restore(self):
        with self.assertRaises(ValueError): self.c.call('finish', {**self.payload, 'phase': 'FAILED_RESTORED'})
    def test_stale_report_does_not_free_slot(self):
        with self.assertRaises(ValueError): self.c.call('finish', {**self.payload, 'token': {**self.t, 'generation': 0}})
        self.assertFalse(self.c.call('status', {})['quiesced'])
    def test_old_incarnation_cannot_settle(self):
        with self.assertRaises(ValueError):self.c.call('finish',{**self.payload,'incarnation':'old','phase':'FAILED_RESTORED','route':{'release':'v1'}})
    def test_canary_requires_samples(self):
        self.c.call('bind', self.payload)
        with self.assertRaises(ValueError): self.c.call('finish', {**self.payload, 'phase': 'COMMITTED'})
        self.c.call('sample', self.sample(1)); self.c.call('sample', self.sample(2))
        self.c.call('authorize_commit', {**self.payload,'phase':'OBSERVING'})
        self.assertTrue(self.c.call('finish', {**self.payload, 'phase': 'COMMITTED'})['quiesced'])
    def test_commit_cannot_bypass_controller_observation(self):
        self.c.call('bind', self.payload)
        with self.assertRaises(ValueError):self.c.call('authorize_commit',{**self.payload,'phase':'OBSERVING'})
        self.c.call('sample',self.sample(1));self.c.call('sample',self.sample(2))
        with self.assertRaises(ValueError):self.c.call('finish',{**self.payload,'phase':'COMMITTED'})
    def test_commit_requires_fresh_observation(self):
        self.c.call('bind',self.payload);self.c.call('sample',self.sample(1));self.c.call('sample',self.sample(2))
        now=self.c.call('status',{})['active']['evidence']['finished_ns']
        with patch('fleetweft.core.time.monotonic_ns',return_value=now+2_000_000_001):
            with self.assertRaises(ValueError):self.c.call('authorize_commit',{**self.payload,'phase':'OBSERVING'})
    def test_duplicate_and_wrong_data_are_rejected(self):
        self.c.call('bind', self.payload); p = self.sample(1)
        with self.assertRaises(ValueError): self.c.call('sample', {**p, 'result': 21})
        self.c.call('sample', p)
        with self.assertRaises(ValueError): self.c.call('sample', p)
    def test_expired_challenge_rejected(self):
        self.c.call('bind', self.payload); p = self.sample(1)
        now = self.c.call('status', {})['active']['challenge_ns']
        with patch('fleetweft.core.time.monotonic_ns', return_value=now + 2_000_000_001):
            with self.assertRaises(ValueError): self.c.call('sample', p)
    def test_incarnation_change_discards_observation(self):
        self.c.call('bind', self.payload); self.c.call('sample', self.sample(1))
        self.c.call('register', {'node': 'a', 'incarnation': 'boot-b', 'expected': 'boot-a'})
        self.assertIsNone(self.c.call('status', {})['active']['evidence'])
        with self.assertRaises(ValueError): self.c.call('sample', self.sample(2))
    def test_delayed_registration_cannot_replace_new_incarnation(self):
        with self.assertRaises(ValueError): self.c.call('register', {'node': 'a', 'incarnation': 'old', 'expected': None})
    def test_restart_requires_reconciliation_and_resets_evidence(self):
        self.c.call('bind', self.payload); self.c.call('sample', self.sample(1))
        old = self.c.call('status', {}); self.c.store.close(); self.c = Controller(self.tmp.name)
        new = self.c.call('status', {})
        self.assertGreater(new['epoch'], old['epoch']); self.assertEqual(new['active']['token'], self.t)
        self.assertTrue(new['active']['needs_reconcile']); self.assertIsNone(new['active']['evidence'])
        with self.assertRaises(ValueError): self.c.call('bind', self.payload)
    def test_old_report_cannot_finish_successor(self):
        self.c.call('finish', {**self.payload, 'phase': 'FAILED_RESTORED', 'route': {'release': 'v1'}})
        self.c.call('resume', {}); self.c.call('plan', {'node': 'a', 'release': 'v3', 'baseline': 'v1'})
        with self.assertRaises(ValueError): self.c.call('finish', {**self.payload, 'phase': 'COMMITTED'})
        self.assertEqual(self.c.call('status', {})['active']['token']['release'], 'v3')


if __name__ == '__main__': unittest.main()
