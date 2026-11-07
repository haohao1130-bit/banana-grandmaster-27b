"""Prepare only the native H3 9B text backend in this experiment's own runtime."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PIN = '56f179f6c50dad0c4c860ae4da427415c8e86415'
MODEL = 'minimax_h3_rewriter_ref2va_qwen3.5_9b_w4a8.safetensors'

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''): h.update(block)
    return h.hexdigest()


def prepare():
    from huggingface_hub import HfApi, hf_hub_download
    import torch
    if not torch.cuda.is_available(): raise RuntimeError('需要 GPU；請在 Colab 選擇 G4。')
    runtime = ROOT/'runtime/native9b'; runtime.mkdir(parents=True, exist_ok=True)
    comfy = runtime/'ComfyUI'
    if not comfy.exists(): subprocess.run(['git','clone','https://github.com/Comfy-Org/ComfyUI.git',str(comfy)], check=True)
    subprocess.run(['git','-C',str(comfy),'checkout','--detach',PIN], check=True)
    subprocess.run([sys.executable,'-m','pip','install','-r',str(comfy/'requirements.txt')], check=True)
    api = HfApi()
    model_repo, guide_repo = 'dseditor/minimax-h3-studio-assets', 'MiniMaxAI/MiniMax-H3'
    revision = api.model_info(model_repo).sha
    guide_rev = api.model_info(guide_repo).sha
    # local_dir yields ordinary files. Never put Hugging Face blob/snapshot caches on Drive.
    source = Path(hf_hub_download(model_repo, filename='text_encoders/'+MODEL,
                                revision=revision, local_dir=str(ROOT/'cache/native9b-download')))
    target = comfy/'models/text_encoders'/MODEL; target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink(): target.unlink()
    # Local symlink only; model and target both live on /content, not Drive.
    target.symlink_to(source.resolve())
    guide = hf_hub_download(guide_repo, filename='docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md',
                           revision=guide_rev, local_dir=str(ROOT/'cache/native9b-guide'))
    shutil.copyfile(guide, runtime/'guide.md')
    manifest = {'model': MODEL, 'model_repository': model_repo, 'model_revision': revision,
                'model_sha256': digest(source), 'model_bytes': source.stat().st_size,
                'guide_repository': guide_repo, 'guide_revision': guide_rev,
                'guide_sha256': digest(runtime/'guide.md'), 'comfy_commit': PIN,
                'torch': torch.__version__, 'cuda': torch.version.cuda,
                'gpu': torch.cuda.get_device_name(0)}
    (runtime/'manifest.json').write_text(json.dumps(manifest, indent=2))
    print('原生 9B 已備妥；尚未載入 GPU。', flush=True)

if __name__ == '__main__': prepare()
