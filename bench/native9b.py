"""Isolated native H3 rewriter experiment; no generic HF model or video sampler."""
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from bench.t8_adapter import load_method
from bench.runner import atomic_json

MODEL = 'minimax_h3_rewriter_ref2va_qwen3.5_9b_w4a8.safetensors'
SYSTEM = ('You enhance prompts for reference-conditioned video and audio generation (Ref2VA). '
          "Infer reference roles from the user's prompt and supplied media. "
          'Preserve intent and explicit constraints while adding relevant visual and sound details. '
          'Follow the guide below and return only its six sections in order, '
          'with plain-text headers on separate lines and no Markdown fences.\n\n')

def sha(data):
    return hashlib.sha256(data).hexdigest()


def graph(system, brief, names, seed=42, max_length=8192):
    content = brief + ''.join(f'\nReference {i+1}: <|vision_start|><|image_pad|><|vision_end|>' for i in range(len(names)))
    chat = f'<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{content.strip()}<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
    nodes = {'encoder': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': MODEL, 'type': 'stable_diffusion', 'device': 'default'}}}
    batch = None
    for i, name in enumerate(names):
        key = f'picture_{i}'
        nodes[key] = {'class_type': 'LoadImage', 'inputs': {'image': name}}
        if batch is None:
            batch = [key, 0]
        else:
            merged = f'batch_{i}'
            nodes[merged] = {'class_type': 'ImageBatch', 'inputs': {'image1': batch, 'image2': [key, 0]}}
            batch = [merged, 0]
    inputs = {'clip': ['encoder', 0], 'prompt': chat, 'max_length': int(max_length),
              'sampling_mode': 'on', 'sampling_mode.temperature': 0.7, 'sampling_mode.top_k': 20,
              'sampling_mode.top_p': 0.8, 'sampling_mode.min_p': 0.0,
              'sampling_mode.repetition_penalty': 1.0, 'sampling_mode.seed': int(seed),
              'sampling_mode.presence_penalty': 0.0, 'thinking': False,
              'use_default_template': True, 'mtp': 'auto'}
    if batch: inputs['image'] = batch
    nodes['generate'] = {'class_type': 'TextGenerate', 'inputs': inputs}
    nodes['result'] = {'class_type': 'PreviewAny', 'inputs': {'source': ['generate', 0]}}
    return nodes


class ComfyBackend:
    def __init__(self, url='http://127.0.0.1:8189', timeout=1800):
        self.url, self.timeout = url.rstrip('/'), timeout

    def request(self, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.url+path, data=data, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def run(self, nodes, progress=lambda _: None):
        info = self.request('/object_info')
        missing = {n['class_type'] for n in nodes.values()} - info.keys()
        if missing: raise RuntimeError('Comfy 缺少節點：'+', '.join(sorted(missing)))
        accepted = self.request('/prompt', {'prompt': nodes, 'client_id': uuid.uuid4().hex})
        if accepted.get('node_errors'): raise RuntimeError(json.dumps(accepted, ensure_ascii=False))
        pid = accepted['prompt_id']
        progress('已排入原生 9B；首次載入權重可能較久。')
        started = time.monotonic()
        deadline = started+self.timeout
        last_notice = started
        while time.monotonic() < deadline:
            history = self.request('/history/'+pid).get(pid)
            if history:
                status = history.get('status', {})
                if status.get('status_str') == 'error': raise RuntimeError(json.dumps(history, ensure_ascii=False))
                if status.get('completed'):
                    value = history.get('outputs', {}).get('result', {}).get('text', [])
                    text = value if isinstance(value, str) else ''.join(value)
                    if not text.strip(): raise RuntimeError('9B 回傳空白：'+json.dumps(history, ensure_ascii=False))
                    return {'status': 'ok', 'text': text, 'prompt_id': pid, 'history': history}
            if time.monotonic()-last_notice >= 15:
                progress(f'9B 執行中：已等待 {int(time.monotonic()-started)} 秒，任務 {pid}。')
                last_notice = time.monotonic()
            time.sleep(1)
        raise TimeoutError(f'等待超時；Comfy 任務 {pid} 可能仍執行。請先查看 native9b.log，勿重複提交。')


def compare(brief, images, output, runtime, seed=42, max_length=8192, order='Off first', backend=None, progress=lambda _: None):
    from PIL import Image, ImageOps
    if not brief.strip(): raise ValueError('請填寫故事與約束。')
    if len(images) > 4: raise ValueError('此對照最多四張參考圖。')
    runtime = Path(runtime)
    guide = (runtime/'guide.md').read_text(encoding='utf-8')
    manifest = json.loads((runtime/'manifest.json').read_text())
    if sha(guide.encode()) != manifest['guide_sha256']: raise ValueError('Guide 與安裝紀錄不符。')
    method, source = load_method()
    systems = {'off': SYSTEM+guide, 'on': SYSTEM+guide+'\n\n'+method}
    run_id = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-native9b-'+uuid.uuid4().hex[:8]
    folder = Path(output)/run_id; folder.mkdir(parents=True)
    input_dir = runtime/'ComfyUI/input'; input_dir.mkdir(parents=True, exist_ok=True)
    names, evidence = [], []
    for i, image in enumerate(images):
        with Image.open(image) as original:
            pic = ImageOps.exif_transpose(original).convert('RGB'); pic.thumbnail((768, 768))
            name = f'{run_id}-{i}.jpg'; pic.save(folder/name, quality=92)
        data = (folder/name).read_bytes(); (input_dir/name).write_bytes(data)
        names.append(name); evidence.append({'name': name, 'sha256': sha(data), 'size': list(pic.size)})
    arms = ['off', 'on'] if order == 'Off first' else ['on', 'off']
    report = {'id': run_id, 'experiment': 'native_h3_9b_t8_off_on_v1', 'model': MODEL,
              'runtime': manifest, 'brief': brief, 'images': evidence, 'systems': systems,
              'system_sha256': {k: sha(v.encode()) for k,v in systems.items()}, 't8_source': source,
              'settings': {'seed': int(seed), 'max_length': int(max_length), 'thinking': False, 'mtp': 'auto'},
              'order': arms, 'arms': {}, 'scope': 'Native H3 9B text only; no audio listening, no video generation or quality acceptance.'}
    path = folder/'report.json'; atomic_json(path, report)
    backend = backend or ComfyBackend()
    for arm in arms:
        nodes = graph(systems[arm], brief, names, seed, max_length)
        atomic_json(folder/(arm+'-graph.json'), nodes)
        progress(arm.upper()+' 執行中；原始輸入已保存。')
        start = time.monotonic()
        try:
            result = backend.run(nodes, progress)
        except Exception as error:
            result = {'status': 'error', 'error_type': type(error).__name__, 'error': str(error)}
        result['seconds'] = time.monotonic()-start
        report['arms'][arm] = result; atomic_json(path, report)
        if result['status'] == 'error':
            # Do not submit another task after an uncertain/failed queue state.
            break
    return report, str(path)
