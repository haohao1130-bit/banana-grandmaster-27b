import json
from pathlib import Path
import tempfile
import unittest

from bench.runner import compare
from bench.tasks import preset,technical_check


class FakeBackend:
    def __init__(self,fail=None):self.calls=[];self.fail=fail
    def run(self,label,system,task,images,settings):
        self.calls.append((label,system,task,images,settings.copy()))
        if label==self.fail:raise RuntimeError('simulated OOM')
        return {'status':'ok','text':'[Shot 1] <Subject 2> slips the punch and counters.','revision':'test-only','metrics':{}}


class BenchTests(unittest.TestCase):
    def test_pair_uses_identical_inputs_sampling_and_saves_real_outputs(self):
        backend=FakeBackend()
        with tempfile.TemporaryDirectory() as temp:
            report,path=compare('writer',preset('writer'),[],{'seed':42,'max_new_tokens':512},temp,backend)
            self.assertEqual([c[0] for c in backend.calls],['9B','27B'])
            self.assertEqual(backend.calls[0][1:],backend.calls[1][1:])
            self.assertEqual(report,json.loads(path.read_text()))
            self.assertFalse(report['visual_verified'])
            self.assertTrue(report['models']['9B']['technical_check']['passed'])

    def test_reverse_order_and_failure_preserve_other_model(self):
        backend=FakeBackend('27B')
        with tempfile.TemporaryDirectory() as temp:
            report,path=compare('writer',preset('writer'),[],{'seed':3,'max_new_tokens':512,'order':'27B first'},temp,backend)
            self.assertEqual([c[0] for c in backend.calls],['27B','9B'])
            self.assertEqual(report['models']['27B']['status'],'error')
            self.assertEqual(report['models']['9B']['status'],'ok')
            self.assertEqual(json.loads(path.read_text())['models']['9B']['revision'],'test-only')

    def test_format_checks_do_not_claim_story_validation(self):
        result=technical_check('writer','[Shot 1] <Subject 2> abandons the promised goal.',preset('writer'))
        self.assertTrue(result['passed']);self.assertFalse(result['visual_verified'])
        self.assertFalse(technical_check('planner','not JSON',preset())['passed'])

    def test_excerpt_and_full_presets_have_distinct_ending_contracts(self):
        self.assertFalse(preset(scope='excerpt')['ending_contract']['finish_work'])
        self.assertEqual(preset()['ending_contract']['resolve_start_by'],60)
        self.assertEqual(len(preset()['segment_template']),8)

    def test_notebook_is_clean_and_all_code_cells_compile(self):
        root=Path(__file__).resolve().parents[1]
        notebook=json.loads((root/'Banana_Grandmaster_27B.ipynb').read_text())
        for cell in notebook['cells']:
            if cell['cell_type']=='code':
                compile(''.join(cell['source']),'colab','exec')
                self.assertEqual(cell['outputs'],[]);self.assertIsNone(cell['execution_count'])


if __name__=='__main__':unittest.main()
