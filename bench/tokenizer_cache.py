"""Inspect/repair only a pinned model's tokenizer.json; never remove weights."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid

SHARED_LINK=re.compile(r'\.\./\.\./blobs/([0-9a-f]{2})/([0-9a-f]{64})')


def inspect_tokenizer(path):
    path=Path(path)
    info={'path':str(path),'resolved_path':str(path.resolve())}
    try:
        data=path.read_bytes()
        info.update(size_bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
                    disk_free_bytes=shutil.disk_usage(path.parent).free)
        if not data:
            info['state']='empty'
        elif data.startswith(b'version https://git-lfs.github.com/spec/v1'):
            info['state']='git_lfs_pointer'
        elif len(data)==79 and SHARED_LINK.fullmatch(data.decode('ascii',errors='replace')):
            info.update(state='shared_blob_link_text',relative_target=data.decode('ascii'))
        else:
            try:
                value=json.loads(data.decode('utf-8'))
                info['state']=('valid_json_structure' if isinstance(value,dict)
                               and isinstance(value.get('model'),dict) else 'invalid_structure')
            except (ValueError,UnicodeError) as error:
                info.update(state='invalid_json',parse_error=str(error))
    except OSError as error:
        info.update(state='unreadable',error=str(error))
    return info


def _shared_target(cached,before):
    """Resolve only this cache's known shared layout, with content-address check."""
    if before['state']!='shared_blob_link_text':return None
    broken=Path(cached).resolve()
    if broken.parent.name!='blobs' or not broken.parent.parent.name.startswith('models--'):
        return None
    match=SHARED_LINK.fullmatch(before['relative_target'])
    if match[1]!=match[2][:2]:return None
    store=(broken.parents[2]/'blobs').resolve()
    target=(broken.parent/before['relative_target']).resolve()
    if not target.is_relative_to(store):return None
    candidate=inspect_tokenizer(target)
    # The per-repo 64-hex LFS etag is the SHA-256 of the actual file, while
    # the shared store uses a different Xet identifier. Do not confuse them.
    if (re.fullmatch(r'[0-9a-f]{64}',broken.name) and
        candidate['state']=='valid_json_structure' and candidate['sha256']==broken.name):
        return target,candidate
    return None


def _materialize(source,destination,expected_sha):
    """Replace the snapshot entry, not its link target, after verifying a copy."""
    destination=Path(destination)
    temp=destination.with_name(destination.name+'.repair-'+uuid.uuid4().hex)
    try:
        shutil.copyfile(source,temp)
        checked=inspect_tokenizer(temp)
        if checked['state']!='valid_json_structure' or checked['sha256']!=expected_sha:
            raise RuntimeError('共享 tokenizer 複製後校驗失敗；保留原快取。')
        os.replace(temp,destination)
    finally:
        temp.unlink(missing_ok=True)


def failure_details(error):
    """Read the actual local tokenizer filename from the failing library frame."""
    tb=error.__traceback__
    while tb:
        name=tb.tb_frame.f_locals.get('fast_tokenizer_file')
        if tb.tb_frame.f_code.co_name=='convert_to_native_format' and isinstance(name,(str,Path)):
            return {'tokenizer_file':inspect_tokenizer(name)}
        tb=tb.tb_next
    return {'tokenizer_file':{'state':'path_not_in_traceback'}}


def repair_from_report(report_path, output_dir, downloader=None):
    from bench.runner import MODELS, atomic_json, failure_record
    report=json.loads(Path(report_path).read_text(encoding='utf-8'))
    if report.get('experiment')!='same_model_t8_storyboard_off_on_v1':
        raise ValueError('請選擇完整 Off／On 對照紀錄 JSON。')
    settings=report.get('settings',{})
    label=settings.get('model_label','27B');revision=settings.get('model_revision')
    if label not in MODELS or not isinstance(revision,str) or not revision:
        raise ValueError('紀錄缺少固定模型 revision，不能改抓其他版本。')
    if not any(isinstance(v,dict) and v.get('error_type')=='JSONDecodeError'
               for v in report.get('arms',{}).values()):
        raise ValueError('此紀錄沒有 JSONDecodeError；不自動修復其他種類的故障。')
    if downloader is None:
        from huggingface_hub import hf_hub_download
        downloader=hf_hub_download
    result={'model':MODELS[label],'revision':revision,'filename':'tokenizer.json',
            'weights_modified':False,'scope':'JSON file validation only, not GPU inference'}
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    record=output_dir/('tokenizer-repair-'+uuid.uuid4().hex[:12]+'.json')
    stage='locating_cached_tokenizer'
    try:
        try:
            cached=downloader(repo_id=MODELS[label],filename='tokenizer.json',
                              revision=revision,local_files_only=True)
        except FileNotFoundError:
            cached=None
        before=inspect_tokenizer(cached) if cached else {'state':'not_cached'}
        result['before']=before
        if before['state']=='valid_json_structure':
            result.update(status='already_valid',downloaded=False)
        else:
            if cached and before['state']=='unreadable':
                raise RuntimeError('無法讀取本機 tokenizer；先檢查權限／掛載，不覆寫未知狀態。')
            if cached:
                stage='backing_up_invalid_tokenizer'
                backup=output_dir/'tokenizer-repair-backups'/(uuid.uuid4().hex+'.json.bak')
                backup.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(cached,backup)
                result['backup']=str(backup)
            stage='checking_shared_tokenizer_payload'
            shared=_shared_target(cached,before) if cached else None
            if shared:
                source,source_info=shared
                stage='materializing_shared_tokenizer'
                _materialize(source,cached,source_info['sha256'])
                downloaded=cached
                result.update(downloaded=False,recovery_method='materialized_existing_shared_blob',
                              recovery_source=source_info)
            else:
                stage='downloading_tokenizer_only'
                downloaded=downloader(repo_id=MODELS[label],filename='tokenizer.json',
                                      revision=revision,force_download=True)
                result.update(downloaded=True,recovery_method='downloaded_pinned_tokenizer')
            stage='validating_replacement'
            result['after']=inspect_tokenizer(downloaded)
            if result['after']['state']!='valid_json_structure':
                raise RuntimeError('重新下載的 tokenizer.json 仍不是有效的 tokenizer JSON；停止重試。')
            result['status']='repaired'
    except Exception as error:
        result['failure']=failure_record(error,MODELS[label],stage)
        result['status']='error'
    atomic_json(record,result)
    return result,record
