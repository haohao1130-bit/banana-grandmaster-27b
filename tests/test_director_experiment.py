import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bench.director_experiment import compare_directors, director_preset, DIRECTOR_SYSTEM
from bench.t8_adapter import load_method


class RecordingBackend:
    def __init__(self, fail_call=None):
        self.calls=[]
        self.fail_call=fail_call

    def run(self, label, system, payload, images, settings):
        self.calls.append((label,system,payload,images,settings.copy()))
        if len(self.calls)==self.fail_call:
            raise RuntimeError('simulated OOM')
        return {'status':'ok','text':'Raw draft '+str(len(self.calls)),
                'revision':'fixed-test-revision','metrics':{}}


class DirectorExperimentTests(unittest.TestCase):
    def execute(self, root, backend, order='Off first'):
        with patch('bench.director_experiment.load_method',return_value=(
                'FIXED_T8_METHOD',{'commit':'test-only'})):
            return compare_directors(director_preset(),[],{
                'seed':42,'max_new_tokens':512,'model_label':'27B','order':order},
                root,'unused',backend)

    def test_one_model_same_inputs_only_system_modifier_changes(self):
        backend=RecordingBackend()
        with tempfile.TemporaryDirectory() as tmp:
            report,path=self.execute(tmp,backend)
            a,b=backend.calls
            self.assertEqual(a[0],b[0]);self.assertEqual(a[0],'27B')
            self.assertEqual(a[2:],b[2:])
            self.assertEqual(a[1],DIRECTOR_SYSTEM)
            self.assertEqual(b[1],a[1]+'\nFIXED_T8_METHOD')
            self.assertEqual(report,json.loads(path.read_text()))
            self.assertEqual(report['arms']['off']['text'],'Raw draft 1')
            self.assertFalse(report['visual_verified'])

    def test_reverse_order_and_partial_failure_are_saved(self):
        backend=RecordingBackend(fail_call=2)
        with tempfile.TemporaryDirectory() as tmp:
            report,path=self.execute(tmp,backend,'On first')
            self.assertTrue(backend.calls[0][1].endswith('FIXED_T8_METHOD'))
            self.assertEqual(report['arms']['on']['text'],'Raw draft 1')
            self.assertEqual(report['arms']['off']['status'],'error')
            self.assertEqual(report,json.loads(path.read_text()))

    def test_first_failure_does_not_skip_second_arm(self):
        with tempfile.TemporaryDirectory() as tmp:
            report,_=self.execute(tmp,RecordingBackend(fail_call=1))
            self.assertEqual(report['arms']['off']['status'],'error')
            self.assertEqual(report['arms']['on']['status'],'ok')

    def test_untrusted_or_missing_t8_source_stops_before_model(self):
        backend=RecordingBackend()
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'upstream.py'
            with self.assertRaisesRegex(ValueError,'尚未準備'):
                load_method(source)
            source.write_text('raise RuntimeError("must never execute")')
            with self.assertRaisesRegex(ValueError,'雜湊不符'):
                compare_directors(director_preset(),[],{'seed':0,'max_new_tokens':512},
                                  tmp,source,backend)
            self.assertEqual(backend.calls,[])

    def test_experiment_notebook_clones_experiment_branch(self):
        root=Path(__file__).resolve().parents[1]
        notebook=json.loads((root/'Banana_T8_Director_AB.ipynb').read_text())
        code='\n'.join(''.join(c['source']) for c in notebook['cells'] if c['cell_type']=='code')
        self.assertIn("SOURCE_REF = 'experiment/t8-director-ab'",code)
        self.assertIn("'--branch',SOURCE_REF",code)
        self.assertIn('actual_ref!=SOURCE_REF',code)
        for cell in notebook['cells']:
            if cell['cell_type']=='code':
                compile(''.join(cell['source']),'colab-experiment','exec')
                self.assertEqual(cell['outputs'],[])


if __name__=='__main__':unittest.main()
