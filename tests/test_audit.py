"""Regression inputs against the production reducer, not a duplicate scheduler."""
import copy
import unittest
from tests import test_mvp as baseline

class AuditContracts(unittest.TestCase):
    setUp=baseline.FleetTests.setUp
    tearDown=baseline.FleetTests.tearDown
    poll=baseline.FleetTests.poll
    deploy=baseline.FleetTests.deploy
    accept=baseline.FleetTests.accept
    success=baseline.FleetTests.success

    def observing(self):
        self.deploy(); self.accept('a',self.poll('a')); self.poll('a')
        r=self.reports['a']; r.update(phase='OBSERVING',route=dict(release='v2',digest='2'*64,worker='anew',port=2))
        for _ in range(2):
            cmd=self.poll('a'); sample={**r,**{k:cmd[k] for k in ('challenge','sequence','input')},'result':14}
            cmd=self.poll('a',sample=sample)
        self.assertEqual(cmd['command'],'commit')
        self.c.call('authorize_commit',r,peer='a')
        return r

    def test_authorized_reply_loss_then_pause_replays_exact_decision(self):
        r=self.observing(); self.c.call('pause',{})
        self.assertEqual(self.poll('a')['command'],'commit')
        try: approval=self.c.call('authorize_commit',r,peer='a')
        except ValueError as exc: self.fail('Lost durable decision: '+str(exc))
        self.assertTrue(approval['active']['commit_authorized'])
        r.update(phase='COMMITTED',committed='v2'); self.poll('a')
        status=self.c.call('status',{})
        self.assertIsNone(status['active']); self.assertTrue(status['paused'])

    def test_authorized_reply_loss_then_rollback_eventually_settles(self):
        r=self.observing(); self.c.call('rollback',{})
        try: approval=self.c.call('authorize_commit',r,peer='a')
        except ValueError as exc: self.fail('Lost durable decision: '+str(exc))
        self.assertTrue(approval['active']['commit_authorized'])
        r.update(phase='COMMITTED',committed='v2'); self.poll('a')
        status=self.c.call('status',{})
        self.assertIsNone(status['active']); self.assertEqual(status['fleet']['mode'],'ROLLBACK')
        self.assertEqual(self.poll('a')['token']['release'],'v1')

    def test_authorized_decision_does_not_allow_new_route(self):
        r=self.observing(); stale=copy.deepcopy(r); stale['route']['worker']='different'
        with self.assertRaises(ValueError): self.c.call('authorize_commit',stale,peer='a')

    def test_terminal_commit_with_failed_probe_settles_but_never_promotes(self):
        r=self.observing(); r.update(phase='COMMITTED',committed='v2')
        self.poll_sequences['a']+=1
        self.c.call('poll',dict(node='a',sequence=self.poll_sequences['a'],status=r,probe=None),peer='a')
        status=self.c.call('status',{})
        self.assertIsNone(status['active']); self.assertTrue(status['paused'])
        self.assertFalse(status['fleet']['canary_passed']); self.assertEqual(status['fleet']['targets']['a'],'FAILED')
        self.assertEqual(status['fleet']['attempts'][-1]['result'],'COMMITTED')
        self.assertFalse(status['fleet']['attempts'][-1]['serving_verified'])
        self.assertEqual(self.poll('b')['command'],'idle')

    def test_unverified_restoration_keeps_occupancy_until_probe_succeeds(self):
        self.deploy(); cmd=self.poll('a'); self.accept('a',cmd); self.c.call('pause',{})
        r=self.reports['a']; r['phase']='FAILED_RESTORED'; self.poll_sequences['a']+=1
        self.c.call('poll',dict(node='a',sequence=self.poll_sequences['a'],status=r,probe=None),peer='a')
        status=self.c.call('status',{})
        self.assertIsNotNone(status['active'])
        self.assertEqual(status['active']['token'],cmd['token']); self.assertEqual(status['occupancy']['state'],'UNKNOWN')
        self.poll('a'); self.assertIsNone(self.c.call('status',{})['active'])

    def test_reordered_poll_cannot_change_captured_rollback_baseline(self):
        r=self.observing(); old=copy.deepcopy(r); sequence=self.poll_sequences['a']
        r.update(phase='COMMITTED',committed='v2'); self.poll('a'); self.success('b'); self.success('c')
        with self.assertRaisesRegex(ValueError,'Stale poll'):
            self.c.call('poll',dict(node='a',sequence=sequence,status=old,probe=dict(result=14,route=old['route'],incarnation=old['incarnation'])),peer='a')
        self.c.call('deploy',{'release':'v3'})
        self.assertEqual(self.c.call('status',{})['fleet']['baseline'],{n:'v2' for n in 'abc'})

    def test_sequence_survives_controller_restart_and_new_boot_can_reset(self):
        self.c.store.close()
        from fleetweft.coordinator import Coordinator
        self.c=Coordinator(self.root,{'v1':'1'*64,'v2':'2'*64,'v3':'3'*64},window=0)
        old=self.reports['a']
        with self.assertRaisesRegex(ValueError,'Stale poll'):
            self.c.call('poll',dict(node='a',sequence=1,status=old,probe=None),peer='a')
        self.poll('a')
        self.reports['a'].update(boot_sequence=2,incarnation='a2')
        self.poll_sequences['a']=0; self.poll('a')
        self.assertEqual(self.c.call('status',{})['registry']['a']['poll_sequence'],1)
