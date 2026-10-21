import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
from fleetweft.artifacts import Artifacts,build,digest
from fleetweft.coordinator import Coordinator
from fleetweft.mvp import provision
from fleetweft.store import Store

class ArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); cls.root=Path(cls.tmp.name)
        for name in ('sign','other'):
            subprocess.run(['openssl','genrsa','-out',str(cls.root/(name+'.key')),'2048'],check=True,capture_output=True)
            subprocess.run(['openssl','rsa','-in',str(cls.root/(name+'.key')),'-pubout','-out',str(cls.root/(name+'.pub'))],check=True,capture_output=True)
        cls.raw=build(b'print("signed")\n','v1',cls.root/'sign.key')
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def setUp(self): self.tmp2=tempfile.TemporaryDirectory(); self.cache=Path(self.tmp2.name)
    def tearDown(self): self.tmp2.cleanup()
    def store(self,raw=None,**kw):
        return Artifacts(self.cache,self.root/'sign.pub',{'v1':digest(raw or self.raw)},**kw)
    def test_signed_cache_revalidated_on_every_use(self):
        a=self.store(); a.install(self.raw,'v1'); p=a.path('v1'); self.assertEqual(p.read_bytes(),b'print("signed")\n')
        p.chmod(0o600); p.write_bytes(b'print("changed")')
        with self.assertRaisesRegex(ValueError,'Cached payload'): a.path('v1')
    def test_wrong_key_with_matching_digest_is_rejected(self):
        raw=build(b'print(1)','v1',self.root/'other.key')
        with self.assertRaisesRegex(ValueError,'signature'): self.store(raw).install(raw,'v1')
        self.assertEqual(list(self.cache.iterdir()),[])
    def test_digest_truncation_rejected(self):
        with self.assertRaisesRegex(ValueError,'digest'): self.store().install(self.raw[:-1],'v1')
    def test_tampered_payload_even_with_new_catalog_digest(self):
        b=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.raw)) as old, zipfile.ZipFile(b,'w') as new:
            for n in old.namelist(): new.writestr(n,b'print(2)' if n=='app.py' else old.read(n))
        raw=b.getvalue()
        with self.assertRaisesRegex(ValueError,'manifest'): self.store(raw).install(raw,'v1')
    def test_unsafe_entries_and_quota(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z: z.writestr('../app.py',b'x')
        with self.assertRaisesRegex(ValueError,'entries'): self.store(b.getvalue()).install(b.getvalue(),'v1')
        with self.assertRaisesRegex(ValueError,'quota'): self.store(quota=1).install(self.raw,'v1')
        self.assertEqual(list(self.cache.iterdir()),[])
    def test_platform_mismatch(self):
        with self.assertRaisesRegex(ValueError,'manifest'): self.store(platform='linux-x86_64').install(self.raw,'v1')
    def test_explicit_provision_does_not_reset_existing_state(self):
        config={'state':str(self.cache/'state')}; uid=provision(config)
        self.assertEqual(len(uid),32)
        with self.assertRaisesRegex(ValueError,'already'): provision(config)

class FleetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.c=Coordinator(self.root,{'v1':'1'*64,'v2':'2'*64,'v3':'3'*64},samples=2,window=0)
        self.reports={}
        for node in 'abc':
            self.c.call('enroll',{'node':node,'node_uuid':node*32})
            self.reports[node]=dict(node_uuid=node*32,boot_sequence=1,incarnation=node+'1',token=None,
                                    phase='IDLE',committed='v1',generation=0,revision=1,workers=[],
                                    route=dict(release='v1',digest='1'*64,port=1,worker=node+'w'))
            self.poll(node)
    def tearDown(self): self.c.store.close(); self.tmp.cleanup()
    def poll(self,node,**kw):
        r=self.reports[node]
        return self.c.call('poll',dict(node=node,status=copy.deepcopy(r),probe=dict(result=14,route=r['route'],incarnation=r['incarnation']),**kw),peer=node)
    def deploy(self): self.c.call('deploy',{'release':'v2'})
    def accept(self,node,cmd):
        r=self.reports[node]; r.update(token=cmd['token'],generation=cmd['token']['generation'],phase='STAGED')
    def success(self,node):
        cmd=self.poll(node); self.accept(node,cmd)
        self.assertEqual(self.poll(node)['command'],'activate')
        r=self.reports[node]; r.update(phase='OBSERVING',route=dict(release=r['token']['release'],digest=r['token']['digest'],worker=node+'new',port=2))
        for _ in range(2):
            cmd=self.poll(node)
            sample={**r,**{k:cmd[k] for k in ('challenge','sequence','input')},'result':14}
            cmd=self.poll(node,sample=sample)
        self.assertEqual(cmd['command'],'commit')
        self.c.call('authorize_commit',r,peer=node)
        r.update(phase='COMMITTED',committed=r['token']['release'])
        self.poll(node)
    def test_canary_must_settle_before_other_nodes(self):
        self.deploy(); self.assertEqual(self.poll('b')['command'],'idle')
        self.success('a'); self.assertEqual(self.c.call('status',{})['fleet']['phase'],'ROLLING')
        self.success('b'); self.success('c')
        self.assertEqual(self.c.call('status',{})['fleet']['phase'],'COMPLETED')
    def test_admission_requires_a_different_fresh_healthy_node(self):
        s=self.c.store.read()
        for n in 'bc': s['registry'][n]['seen_ns']=0
        self.c.store.save(s); self.deploy()
        self.assertEqual(self.poll('a')['command'],'idle')
        self.poll('b'); self.assertEqual(self.poll('a')['command'],'accept')
        s=self.c.store.read(); s['registry']['a']['seen_ns']=0; self.c.store.save(s)
        self.assertEqual(self.c.call('status',{})['occupancy']['state'],'UNKNOWN')

    def test_bad_canary_restores_and_pauses(self):
        self.deploy(); cmd=self.poll('a'); self.accept('a',cmd); self.poll('a')
        r=self.reports['a']; r.update(phase='OBSERVING',route=dict(release='v2',digest='2'*64,worker='bad',port=2))
        cmd=self.poll('a'); sample={**r,**{k:cmd[k] for k in ('challenge','sequence','input')},'result':21}
        self.assertEqual(self.poll('a',sample=sample)['command'],'cancel')
        self.assertEqual(self.poll('b')['command'],'idle')
        r.update(phase='FAILED_RESTORED',route=dict(release='v1',digest='1'*64,worker='old',port=1)); self.poll('a')
        self.assertTrue(self.c.call('status',{})['paused'])
    def test_lost_contact_retains_occupancy(self):
        self.deploy(); token=self.poll('a')['token']; self.c.call('pause',{})
        self.assertEqual(self.poll('b')['command'],'idle')
        self.assertEqual(self.c.call('status',{})['active']['token'],token)
        self.assertEqual(self.poll('a')['command'],'refuse')
    def test_controller_restart_requires_reconciliation(self):
        self.deploy(); cmd=self.poll('a'); self.accept('a',cmd)
        self.c.store.close(); self.c=Coordinator(self.root,self.c.digests,window=0)
        self.assertEqual(self.poll('a')['command'],'cancel')
        self.assertTrue(self.c.call('status',{})['paused'])
    def test_stale_boot_and_cross_node_identity_rejected(self):
        self.reports['a'].update(boot_sequence=0)
        with self.assertRaisesRegex(ValueError,'boot'): self.poll('a')
        with self.assertRaisesRegex(ValueError,'authenticated'): self.c.call('poll',dict(node='a'),peer='b')
        with self.assertRaisesRegex(ValueError,'Operator'): self.c.call('deploy',{'release':'v2'},peer='a')
    def test_lost_node_state_rejected(self):
        self.reports['a']['node_uuid']='f'*32
        with self.assertRaisesRegex(ValueError,'lost'): self.poll('a')
    def test_grant_and_fleet_atomic_on_dispatch_error(self):
        before=self.c.store.read()
        with self.assertRaises(ValueError): self.c.call('deploy',{'release':'invalid'})
        self.assertEqual(self.c.store.read(),before)
    def test_rollback_is_higher_generation_and_keeps_offline_incomplete(self):
        self.deploy(); self.success('a'); self.c.call('rollback',{})
        cmd=self.poll('a'); self.assertEqual(cmd['token']['release'],'v1')
        self.assertEqual(cmd['token']['baseline'],'v2'); self.assertGreater(cmd['token']['generation'],1)
        self.assertNotEqual(self.c.call('status',{})['fleet']['phase'],'ROLLED_BACK')
    def test_offline_ungranted_target_remains_in_original_history(self):
        self.deploy(); self.success('a'); self.success('b')
        s=self.c.store.read(); s['registry']['c']['seen_ns']=0; self.c.store.save(s)
        self.poll('a'); self.assertEqual(self.c.call('status',{})['fleet']['targets']['c'],'DEFERRED')
        self.c.call('deploy',{'release':'v3'})
        old=self.c.call('status',{})['history'][-1]
        self.assertEqual(old['phase'],'SUPERSEDED_INCOMPLETE'); self.assertEqual(old['targets']['c'],'DEFERRED')

class WorkerStartupTests(unittest.TestCase):
    def test_partial_readiness_is_bounded_and_failed_worker_reaped(self):
        from unittest.mock import patch
        from fleetweft.node import Node
        import time
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); script=root/'app.py'
            script.write_text('import sys,time\nsys.stdout.write("x");sys.stdout.flush();time.sleep(30)\n')
            class Cache:
                catalog={'v1':'1'*64}
                def path(self,release): return script
            node=Node.__new__(Node); node.artifacts=Cache(); node.name='a'; node.children=[]
            node.store=Store(root/'state',{'children':[]})
            try:
                started=time.monotonic()
                with patch('fleetweft.node.identity',return_value={'pid':999,'start':1,'boot':'test'}), patch('fleetweft.node.WORKER_START_TIMEOUT',.1):
                    with self.assertRaisesRegex(ValueError,'startup'): node.spawn('v1')
                self.assertLess(time.monotonic()-started,3)
                self.assertEqual(node.children,[]); self.assertEqual(node.store.read()['children'],[])
            finally: node.store.close()

class MVPReportTests(unittest.TestCase):
    def test_partial_report_does_not_render_pass(self):
        from tools.mvp_report import render
        text=render({'passed':True,'source':{},'guest':{'cases':[]}})
        self.assertIn('INCOMPLETE/FAIL',text)
        self.assertNotIn('evidence: PASS',text)

class AtomicFleetTests(unittest.TestCase):
    setUp=FleetTests.setUp
    tearDown=FleetTests.tearDown
    poll=FleetTests.poll
    deploy=FleetTests.deploy
    accept=FleetTests.accept
    success=FleetTests.success
    def test_settlement_error_keeps_durable_grant(self):
        from unittest.mock import patch
        self.deploy(); disk=self.c.store; before=[]; event=self.c.event
        def failing_event(kind,**fields):
            if kind=='SETTLED':
                before.append(disk.read()); raise ValueError('injected event persistence boundary')
            return event(kind,**fields)
        with patch.object(self.c,'event',side_effect=failing_event):
            with self.assertRaisesRegex(ValueError,'persistence boundary'): self.success('a')
        self.assertIsNotNone(disk.read()['active'])
        self.assertEqual(disk.read(),before[0])
