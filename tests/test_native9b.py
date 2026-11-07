import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from bench.native9b import graph, compare, sha, MODEL, ComfyBackend

class Native9BTests(unittest.TestCase):
    def test_native_graph_matches_image_contract(self):
        nodes=graph('guide','story',['a.jpg','b.jpg'])
        self.assertEqual(nodes['encoder']['inputs']['clip_name'],MODEL)
        self.assertEqual(nodes['generate']['inputs']['image'],['batch_1',0])
        self.assertEqual(nodes['generate']['inputs']['prompt'].count('<|image_pad|>'),2)
        self.assertFalse(nodes['generate']['inputs']['thinking'])
        self.assertEqual(nodes['generate']['inputs']['sampling_mode.seed'],42)
        self.assertEqual({v['class_type'] for v in nodes.values()}, {'CLIPLoader','LoadImage','ImageBatch','TextGenerate','PreviewAny'})

    def test_pair_only_changes_system_and_preserves_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); runtime=root/'runtime';runtime.mkdir()
            (runtime/'guide.md').write_text('guide')
            (runtime/'manifest.json').write_text(json.dumps({'guide_sha256':sha(b'guide')}))
            image=root/'pic.png';Image.new('RGB',(1000,500)).save(image)
            class Backend:
                def __init__(self):self.calls=[]
                def run(self,nodes,progress):self.calls.append(nodes);return {'status':'ok','text':'raw result'}
            backend=Backend()
            with patch('bench.native9b.load_method',return_value=('T8 method',{'commit':'pinned'})):
                report,path=compare('story',[image],root/'runs',runtime,backend=backend)
            self.assertEqual(len(backend.calls),2)
            a,b=backend.calls
            self.assertEqual(b['generate']['inputs'].pop('prompt'),a['generate']['inputs'].pop('prompt').replace('guide<|im_end|>','guide\n\nT8 method<|im_end|>'))
            self.assertEqual(a,b)
            self.assertEqual(report['images'][0]['size'],[768,384])
            self.assertTrue(Path(path).exists())
            self.assertEqual(report['arms']['off']['text'],'raw result')

    def test_failure_stops_second_queue_and_saves_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'guide.md').write_text('guide');(root/'manifest.json').write_text(json.dumps({'guide_sha256':sha(b'guide')}))
            class Backend:
                def run(self,*args):raise TimeoutError('pending')
            with patch('bench.native9b.load_method',return_value=('method',{})):
                report,path=compare('story',[],root/'runs',root,backend=Backend())
            self.assertEqual(list(report['arms']),['off'])
            self.assertEqual(json.loads(Path(path).read_text())['arms']['off']['error_type'],'TimeoutError')

    def test_history_extraction(self):
        backend=ComfyBackend()
        def request(path,body=None):
            if path=='/object_info':return {'CLIPLoader':{},'TextGenerate':{},'PreviewAny':{}}
            if path=='/prompt':return {'prompt_id':'x'}
            return {'x':{'status':{'completed':True},'outputs':{'result':{'text':['a','b']}}}}
        backend.request=request
        self.assertEqual(backend.run(graph('s','b',[]))['text'],'ab')

    def test_notebooks_have_no_generic_model_execution(self):
        root=Path(__file__).resolve().parents[1]
        for name in ('Banana_9B_T8_AB.ipynb','Banana_T8_Director_AB.ipynb','Banana_Grandmaster_27B.ipynb'):
            notebook=json.loads((root/name).read_text())
            for i,cell in enumerate(notebook['cells']):
                if cell['cell_type']=='code':compile(''.join(cell['source']),f'{name}:{i}','exec')
            text=json.dumps(notebook)
            self.assertNotIn('AutoProcessor',text)
            self.assertNotIn('Qwen/Qwen3.5-27B',text)

if __name__=='__main__':unittest.main()
