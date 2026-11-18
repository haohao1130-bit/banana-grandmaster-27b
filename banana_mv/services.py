"""Banana-owned settings, compatible asset storage and local prompt rewriting."""
import copy
import json
import os
import random
import shutil
import threading
import time
import urllib.request
import uuid
from pathlib import Path

from banana_mv.comfy import comfy, queue_prompt as _comfy_queue_prompt, history_entry, execution_error, comfy_download, wait_prompt
from banana_mv import llama27b
from banana_mv.core import probe

ROOT = Path(__file__).resolve().parents[1]
# Legacy environment is accepted only to keep existing local launchers/data usable.
DATA = Path(os.environ.get('BANANA_DATA') or os.environ.get('H3TOYBOX_DATA') or '/content/banana_mv_data')
LIBRARY = DATA/'library'
PORT = int(os.environ.get('BANANA_PORT', '8190'))
ASSET_LOCK = threading.Lock()
DEFAULTS = {
    'comfy_url': 'http://127.0.0.1:8188',
    'comfy_input_dir': '/content/ComfyUI/input',
    'guides': {'ref': str(ROOT/'guides/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md')},
    'free_after_rewrite': True,
    'rewriter': {'model': str(llama27b.DEFAULT_MODEL), 'mmproj': str(llama27b.DEFAULT_MMPROJ),
                 'server': str(llama27b.DEFAULT_SERVER), 'port': 8217,
                 'gpu_layers': 12, 'context': 32768, 'max_length': 4096,
                 'temperature': 0.4, 'top_p': 0.8},
}


def load_config():
    cfg = copy.deepcopy(DEFAULTS)
    path = DATA/'config.json'
    saved = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    # Import only settings used by Banana. Remote provider credentials are never loaded.
    for key in ('comfy_url', 'comfy_input_dir', 'free_after_rewrite'):
        if key in saved:
            cfg[key] = saved[key]
    for key in cfg['rewriter']:
        if key in saved.get('rewriter', {}):
            cfg['rewriter'][key] = saved['rewriter'][key]
    # Earlier 27B one-click installs persisted the old 8K default.
    # Lift ONLY that known legacy default to 32K; keep custom user values.
    if int(cfg['rewriter'].get('context', 32768)) == 8192:
        cfg['rewriter']['context'] = 32768
    return cfg


def safe_child(root, relative):
    root = Path(root).resolve()
    child = (root/relative).resolve()
    if not child.is_relative_to(root) or child == root:
        raise ValueError('無效的檔案路徑。')
    return child


def library_index():
    path = LIBRARY/'library.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else []


def asset(asset_id):
    item = next((row for row in library_index() if row['id'] == asset_id), None)
    if item is None:
        raise ValueError('找不到素材，請重新上傳。')
    safe_child(LIBRARY, item['file'])
    safe_child(Path(load_config()['comfy_input_dir']), item['comfy_name'])
    return item


def restore_inputs(cfg):
    inp = Path(cfg['comfy_input_dir']); inp.mkdir(parents=True, exist_ok=True)
    restored = 0
    for item in library_index():
        source = safe_child(LIBRARY, item['file'])
        dest = safe_child(inp, item['comfy_name'])
        if source.is_file() and not dest.exists():
            shutil.copyfile(source, dest); restored += 1
    return restored


def add_asset(cfg, filename, body):
    suffix = Path(filename).suffix.lower()
    image = suffix in ('.png', '.jpg', '.jpeg', '.webp')
    if not image and suffix not in ('.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac', '.mp4', '.webm'):
        raise ValueError('請上傳 PNG/JPEG/WebP 圖片或支援的音訊檔。')
    LIBRARY.mkdir(parents=True, exist_ok=True)
    aid = uuid.uuid4().hex[:12]
    stored = LIBRARY/(aid+suffix)
    inp = Path(cfg['comfy_input_dir']); inp.mkdir(parents=True, exist_ok=True)
    name = 'banana_asset_' + stored.name
    target = inp/name
    try:
        stored.write_bytes(body)
        row = {'id': aid, 'name': Path(filename).name, 'file': stored.name,
               'comfy_name': name, 'created': time.time(), 'kind': 'image' if image else 'audio'}
        if image:
            from PIL import Image, ImageOps
            with Image.open(stored) as pic:
                pic.load()
                row['width'], row['height'] = ImageOps.exif_transpose(pic).size
        elif not any(s['codec_type']=='audio' for s in probe(stored)['streams']):
            raise ValueError('檔案內沒有音軌。')
        shutil.copyfile(stored, target)
        with ASSET_LOCK:
            index = library_index()
            index.insert(0, row)
            temp = LIBRARY/'library.json.tmp'
            temp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(LIBRARY/'library.json')
        return row
    except Exception as error:
        stored.unlink(missing_ok=True); target.unlink(missing_ok=True)
        if image and isinstance(error, OSError):
            raise ValueError('無法讀取圖片，請重新匯出 PNG/JPEG/WebP。') from None
        raise


def active_rewrite_prompt_id():
    """27B requests are owned by llama.cpp, not ComfyUI prompt IDs."""
    return None


def cancel_27b():
    llama27b.stop(cancel=True)


def release_27b():
    """Required memory handoff before *every* H3 job, even when resuming."""
    llama27b.stop()


def queue_prompt(cfg, graph):
    """Comfy entrypoint: free the exclusive 27B worker before H3 sampling."""
    release_27b()
    return _comfy_queue_prompt(cfg, graph)


def rewrite_local(cfg, system, parts, job_id):
    """Unload Comfy H3 caches before 27B; never fall back to 9B."""
    # The previous H3 clip can leave weights cached in the *other* GPU process.
    # /free is a Comfy-owned request; it does not kill or unload our llama worker.
    comfy(cfg, '/free', {'unload_models': True, 'free_memory': True})
    return llama27b.generate(cfg, system, parts, job_id)


def upload_comfy_image(cfg, name, data, content_type):
    boundary = uuid.uuid4().hex
    header = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; '
              f'filename="{name}"\r\nContent-Type: {content_type}\r\n\r\n')
    body = header.encode() + data + f'\r\n--{boundary}--\r\n'.encode()
    request = urllib.request.Request(cfg['comfy_url'].rstrip('/') + '/upload/image',
        data=body, headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    with urllib.request.urlopen(request, timeout=30) as response:
        uploaded = json.load(response)
    return '/'.join(filter(None, (uploaded.get('subfolder'), uploaded['name'])))
