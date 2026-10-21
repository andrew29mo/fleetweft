import copy
import subprocess
import sys
import unittest
from tools.report import rejection,external,render,verify_mutations


class ReportContracts(unittest.TestCase):
    def test_execution_errors_cannot_count_as_protocol_rejection(self):
        rejection({'exit_code':17,'http_status':409})
        for value in ({'exit_code':-9,'http_status':409},{'exit_code':17,'http_status':503},
                      {'exit_code':255},{'exit_code':18,'transport_error':'URLError'}):
            with self.assertRaises(AssertionError):rejection(value)

    def test_http_release_alone_is_not_application_correctness(self):
        value={'release':'v2','worker':'worker','result':14,'healthy':True,'challenge':'external-probe',
               'incarnation':'boot','route':{'release':'v2','worker':'worker','port':1234,'digest':'f'*64}}
        external(value,'v2')
        for change in (lambda x:x.update(result=21),lambda x:x.update(worker='other'),
                       lambda x:x['route'].update(release='v1'),lambda x:x.update(challenge='stale')):
            wrong=copy.deepcopy(value);change(wrong)
            with self.assertRaises(AssertionError):external(wrong,'v2')

    def test_incomplete_report_cannot_render_success(self):
        value=render({'passed':True,'source':{},'cases':['<script>']})
        self.assertIn('FAIL / INCOMPLETE',value);self.assertNotIn('<script>',value)

    def test_optimized_validation_is_refused(self):
        result=subprocess.run([sys.executable,'-O','-c','import tools.report'],capture_output=True,text=True,timeout=3)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Evidence checks require assertions',result.stderr)

    def test_mutation_receipt_requires_complete_unique_controls(self):
        from tools.mutations import MUTATIONS
        value={'passed':True,'source':{},'rows':[{'name':name,'test':test,'caught_by_assertion':True,'exit_code':1} for _,name,_,_,test in MUTATIONS]}
        verify_mutations(value,{})
        for change in (lambda x:x['rows'].pop(),lambda x:x['rows'].append(x['rows'][0]),
                       lambda x:x['rows'][0].update(test='other'),lambda x:x['rows'][0].update(exit_code=0)):
            wrong=copy.deepcopy(value);change(wrong)
            with self.assertRaises(AssertionError):verify_mutations(wrong,{})
