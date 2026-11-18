"""Exercise owned storage and local rewriter without upstream files or a GPU."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from banana_mv import services


class ServicesTests(unittest.TestCase):
    def test_existing_library_restore_and_path_safety(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);lib=root/'library';lib.mkdir();inp=root/'input'
            with patch.object(services,'DATA',root),patch.object(services,'LIBRARY',lib):
                (root/'config.json').write_text(json.dumps({'comfy_input_dir':str(inp),
                    'rewriter':{'openai':{'api_key':'do-not-load'},'temperature':0.5},
                    'guides':{'ref':'old/frontend/guide.md'}}))
                (lib/'old.png').write_bytes(b'preserved-original')
                (lib/'library.json').write_text(json.dumps([{'id':'legacy','file':'old.png','comfy_name':'h3fe_old.png'}]))
                cfg=services.load_config()
                self.assertNotIn('openai',cfg['rewriter'])
                self.assertEqual(cfg['rewriter']['temperature'],0.5)
                self.assertNotIn('old/frontend',cfg['guides']['ref'])
                self.assertEqual(services.restore_inputs(cfg),1)
                self.assertEqual((inp/'h3fe_old.png').read_bytes(),b'preserved-original')
                self.assertEqual(services.asset('legacy')['file'],'old.png')
                with self.assertRaises(ValueError):services.safe_child(lib,'../config.json')
                with self.assertRaises(ValueError):services.add_asset(cfg,'bad.png',b'not an image')
                self.assertEqual(len(services.library_index()),1)

    def test_legacy_8k_director_context_migrates_to_32k(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            path = data / 'config.json'
            with patch.object(services, 'DATA', data):
                path.write_text(json.dumps({'rewriter': {'context': 8192}}))
                self.assertEqual(services.load_config()['rewriter']['context'], 32768)
                path.write_text(json.dumps({'rewriter': {'context': 8192, 'gpu_layers': 12}}))
                migrated = services.load_config()['rewriter']
                self.assertEqual(migrated['context'], 32768)
                self.assertEqual(migrated['gpu_layers'], 999)
                path.write_text(json.dumps({'rewriter': {'context': 32768, 'gpu_layers': 'auto'}}))
                self.assertEqual(services.load_config()['rewriter']['gpu_layers'], 999)
                path.write_text(json.dumps({'rewriter': {'context': 32768, 'gpu_layers': 35}}))
                self.assertEqual(services.load_config()['rewriter']['gpu_layers'], 999)
                path.write_text(json.dumps({'rewriter': {'context': 32768, 'gpu_layers': 25}}))
                self.assertEqual(services.load_config()['rewriter']['gpu_layers'], 25)
                path.write_text(json.dumps({'rewriter': {'context': 65536}}))
                self.assertEqual(services.load_config()['rewriter']['context'], 65536)

    def test_27b_exclusive_dispatch_and_h3_handoff(self):
        cfg=services.load_config()
        self.assertIn('27B',cfg['rewriter']['model'])
        pics=[Image.new('RGB',(64,64),c) for c in ('red','blue')]
        parts=[('text','<Picture 1>'),('image',pics[0]),('text','<Picture 2>'),('image',pics[1])]
        with patch.object(services.llama27b,'generate',return_value='hello') as director, \
             patch.object(services,'comfy',return_value={}) as free:
            self.assertEqual(services.rewrite_local(cfg,'guide',parts,'test'),'hello')
            director.assert_called_once_with(cfg,'guide',parts,'test')
            free.assert_called_once_with(cfg,'/free',{'unload_models':True,'free_memory':True})
        with patch.object(services.llama27b,'stop') as release, \
             patch.object(services,'_comfy_queue_prompt',return_value='h3-prompt') as queue:
            self.assertEqual(services.queue_prompt(cfg,{'1':{}}),'h3-prompt')
            release.assert_called_once_with()
            queue.assert_called_once_with(cfg,{'1':{}})
        with patch.object(services.llama27b,'stop') as stop:
            services.cancel_27b()
            stop.assert_called_once_with(cancel=True)
