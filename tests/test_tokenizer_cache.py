import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from bench.tokenizer_cache import inspect_tokenizer, failure_details, repair_from_report


VALID=b'{"model":{"type":"BPE","vocab":{},"merges":[]}}'


class TokenizerCacheTests(unittest.TestCase):
    def report(self,root):
        p=root/'original.json'
        p.write_text(json.dumps({'experiment':'same_model_t8_storyboard_off_on_v1',
            'settings':{'model_label':'27B','model_revision':'pinned-test-revision'},
            'arms':{'off':{'status':'ok','text':'keep this'},
                    'on':{'status':'error','error_type':'JSONDecodeError'}}}))
        return p

    def test_invalid_file_is_backed_up_and_only_pinned_tokenizer_is_downloaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cached=root/'tokenizer.json';cached.write_bytes(b'')
            weight=root/'model.safetensors';weight.write_bytes(b'weight sentinel')
            report=self.report(root);original=report.read_bytes();calls=[]
            def download(**kwargs):
                calls.append(kwargs)
                if kwargs.get('force_download'):cached.write_bytes(VALID)
                return str(cached)
            result,record=repair_from_report(report,root,download)
            self.assertEqual(result['status'],'repaired')
            self.assertEqual(result['before']['state'],'empty')
            self.assertEqual(Path(result['backup']).read_bytes(),b'')
            self.assertEqual(weight.read_bytes(),b'weight sentinel')
            self.assertEqual(report.read_bytes(),original)
            self.assertEqual(result,json.loads(record.read_text()))
            self.assertEqual(len(calls),2)
            self.assertTrue(all(c['filename']=='tokenizer.json' and
                                c['revision']=='pinned-test-revision' for c in calls))

    def test_valid_json_is_not_redownloaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cached=root/'tokenizer.json';cached.write_bytes(VALID);calls=[]
            def download(**kwargs):calls.append(kwargs);return str(cached)
            result,_=repair_from_report(self.report(root),root,download)
            self.assertEqual(result['status'],'already_valid')
            self.assertEqual(len(calls),1)
            self.assertTrue(calls[0]['local_files_only'])

    def test_traceback_identifies_actual_bad_file_without_guessing(self):
        def convert_to_native_format(fast_tokenizer_file):
            with open(fast_tokenizer_file) as handle:json.load(handle)
        with tempfile.TemporaryDirectory() as tmp:
            bad=Path(tmp)/'actual-tokenizer.json';bad.write_bytes(b'not json')
            try:convert_to_native_format(str(bad))
            except json.JSONDecodeError as error:details=failure_details(error)
            self.assertEqual(details['tokenizer_file']['path'],str(bad))
            self.assertEqual(details['tokenizer_file']['state'],'invalid_json')

    def test_failed_download_preserves_invalid_backup_and_reports_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cached=root/'tokenizer.json';cached.write_bytes(b'broken')
            def download(**kwargs):
                if kwargs.get('force_download'):raise OSError('simulated network failure')
                return str(cached)
            result,_=repair_from_report(self.report(root),root,download)
            self.assertEqual(result['status'],'error')
            self.assertEqual(result['failure']['stage'],'downloading_tokenizer_only')
            self.assertEqual(Path(result['backup']).read_bytes(),b'broken')
            self.assertEqual(cached.read_bytes(),b'broken')

    def test_drive_shared_link_text_recovers_existing_payload_without_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);hub=root/'hub';repo=hub/'models--Qwen--Qwen3.5-27B'
            etag=hashlib.sha256(VALID).hexdigest();xet='8f'+'1'*62
            target=hub/'blobs'/'8f'/xet;target.parent.mkdir(parents=True);target.write_bytes(VALID)
            broken=repo/'blobs'/etag;broken.parent.mkdir(parents=True)
            pointer='../../blobs/8f/'+xet;broken.write_text(pointer)
            snapshot=repo/'snapshots'/'pinned-test-revision'/'tokenizer.json'
            snapshot.parent.mkdir(parents=True);snapshot.symlink_to('../../blobs/'+etag)
            self.assertEqual(inspect_tokenizer(snapshot)['size_bytes'],79)
            self.assertEqual(inspect_tokenizer(snapshot)['state'],'shared_blob_link_text')
            calls=[]
            def download(**kwargs):
                calls.append(kwargs)
                if kwargs.get('force_download'):self.fail('Valid existing payload must not be redownloaded')
                return str(snapshot)
            result,_=repair_from_report(self.report(root),root/'runs',download)
            self.assertEqual(result['status'],'repaired')
            self.assertEqual(result['recovery_method'],'materialized_existing_shared_blob')
            self.assertFalse(result['downloaded'])
            self.assertFalse(snapshot.is_symlink())
            self.assertEqual(snapshot.read_bytes(),VALID)
            self.assertEqual(target.read_bytes(),VALID)
            self.assertEqual(broken.read_text(),pointer)
            self.assertEqual(Path(result['backup']).read_bytes(),pointer.encode())
            self.assertEqual(len(calls),1)

    def test_shared_payload_hash_mismatch_is_not_silently_materialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);hub=root/'hub';repo=hub/'models--Qwen--Qwen3.5-27B'
            target=hub/'blobs'/'8f'/('8f'+'1'*62);target.parent.mkdir(parents=True);target.write_bytes(VALID)
            broken=repo/'blobs'/('a'*64);broken.parent.mkdir(parents=True)
            broken.write_text('../../blobs/8f/'+target.name)
            calls=[]
            def download(**kwargs):
                calls.append(kwargs)
                if kwargs.get('force_download'):broken.write_bytes(VALID)
                return str(broken)
            result,_=repair_from_report(self.report(root),root/'runs',download)
            self.assertEqual(result['recovery_method'],'downloaded_pinned_tokenizer')
            self.assertEqual(len(calls),2)


if __name__=='__main__':unittest.main()
