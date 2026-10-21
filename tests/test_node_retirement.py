import copy
import threading
import unittest
from unittest.mock import Mock,patch
from fleetweft.node import Node


class RetirementContracts(unittest.TestCase):
    def test_borrowed_request_finishes_before_worker_is_retired(self):
        borrowed=threading.Event();release=threading.Event();waiting=threading.Event()
        class ObservedCondition(threading.Condition):
            def wait(self,timeout=None):
                waiting.set();return super().wait(timeout)
        node=Node.__new__(Node);node.routes=ObservedCondition();node.lock=threading.RLock()
        node.inflight={};node.incarnation='boot'
        old_route={'worker':'old','release':'v1','port':1234,'digest':'f'*64}
        new_route={**old_route,'worker':'new','release':'v2','port':2345}
        node.route=old_route
        old=Mock(args=['worker','old'],pid=123);new=Mock(args=['worker','new'],pid=234)
        old.poll.return_value=None;new.poll.return_value=None
        node.children=[old,new]
        node.store=Mock();node.store.read.return_value={'children':[{'pid':123},{'pid':234}]}
        errors=[];responses=[]
        def slow(*args):
            borrowed.set()
            if not release.wait(2):raise RuntimeError('Test release timeout')
            return {'worker':'old','release':'v1','result':14}
        def work():
            try:responses.append(node.work(7,'challenge'))
            except BaseException as e:errors.append(e)
        def retire():
            try:
                with node.lock:node.retire_obsolete()
            except BaseException as e:errors.append(e)
        with patch('fleetweft.node.request',side_effect=slow),patch('fleetweft.node.identity',side_effect=lambda pid:{'pid':pid}):
            reader=threading.Thread(target=work);writer=threading.Thread(target=retire)
            reader.start()
            try:
                self.assertTrue(borrowed.wait(1));node.switch(new_route);writer.start()
                self.assertTrue(waiting.wait(1),'Retirement skipped its active-request wait')
                old.kill.assert_not_called();self.assertTrue(writer.is_alive())
            finally:
                release.set();reader.join(3)
                if writer.ident is not None:writer.join(3)
        self.assertFalse(reader.is_alive());self.assertFalse(writer.is_alive());self.assertFalse(errors)
        self.assertEqual(responses[0]['route'],old_route)
        old.kill.assert_called_once();old.wait.assert_called_once();new.kill.assert_not_called()
        self.assertEqual(node.children,[new]);self.assertEqual(node.inflight,{})
        self.assertEqual(node.store.save.call_args.args[0]['children'],[{'pid':234}])
