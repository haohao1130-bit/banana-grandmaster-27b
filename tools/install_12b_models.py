"""Install ONLY Gemma 3 12B IT Q5 and its matching F16 projector.

All existing H3 models stay in F:/AI/BANANAMV_27B_STUDIO/Models/H3,
and all shared CUDA/ComfyUI runtimes remain read-only from this installer.
"""
import argparse
import json
import os
from pathlib import Path
from huggingface_hub import hf_hub_download, HfApi

MANIFEST = [
    ("bartowski/google_gemma-3-12b-it-GGUF", "google_gemma-3-12b-it-Q5_K_M.gguf", "12B"),
    ("bartowski/google_gemma-3-12b-it-GGUF", "mmproj-google_gemma-3-12b-it-f16.gguf", "12B"),
]

def download_all(root):
    root = Path(root)
    api = HfApi()
    for i, (repo, filename, subdir) in enumerate(MANIFEST, 1):
        folder = root / Path(subdir)
        folder.mkdir(parents=True, exist_ok=True)
        local = folder / filename
        print("[%s/%s] %s :: %s" % (i, len(MANIFEST), repo, filename), flush=True)
        # Verify expected size when upstream publishes it, to avoid trusting a
        # truncated .gguf/.safetensors after interrupted downloads.
        info = api.model_info(repo, files_metadata=True)
        entry = next((f for f in info.siblings if f.rfilename == filename), None)
        if entry is None:
            raise FileNotFoundError("Upstream model file not found: %s/%s" % (repo, filename))
        size = getattr(entry, "size", None)
        if local.is_file() and size and local.stat().st_size == size:
            print("  present; verified size: %s" % size, flush=True)
            continue
        if local.exists() and size and local.stat().st_size != size:
            print("  size mismatch; resuming/repairing", flush=True)
            local.unlink()
        saved = Path(hf_hub_download(repo_id=repo, filename=filename, local_dir=folder,
                                     force_download=False))
        if size and saved.stat().st_size != size:
            raise IOError("Downloaded model size mismatch: %s (%s != %s)" % (saved, saved.stat().st_size, size))
        if saved.stat().st_size == 0:
            raise IOError("Downloaded file is empty: " + str(saved))
        print("  ready: " + str(saved), flush=True)
    (root / "install-models-ok.json").write_text(
        json.dumps({"files": [name for _, name, _ in MANIFEST]}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--models-root", default=r"F:\BANANAMV_12B_STUDIO\Models")
    args = p.parse_args()
    download_all(args.models_root)
