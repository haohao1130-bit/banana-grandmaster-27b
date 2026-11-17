"""One-click, resumable download manifest for the isolated 27B studio.

H3 files mirror the actual banana_mv.core.MODELS and MOTION_LORAS names.
Do not download the specialized 9B rewriter for this experimental branch.
"""
import argparse
import json
import os
from pathlib import Path
from huggingface_hub import hf_hub_download, HfApi

MANIFEST = [
    ("unsloth/Qwen3.5-27B-GGUF", "Qwen3.5-27B-Q4_K_M.gguf", "27B"),
    ("unsloth/Qwen3.5-27B-GGUF", "mmproj-BF16.gguf", "27B"),
    ("OliviaRossi/Minimax-h3_Singularity-x-10Eros-Max_PRISM",
     "Minimax-h3_Singularity_x_10Eros-Max_PRISM_int8.safetensors", "H3/diffusion_models"),
    ("Comfy-Org/MiniMax-H3", "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "H3"),
    ("Comfy-Org/MiniMax-H3", "vae/minimax_h3_video_vae_int8_convrot.safetensors", "H3"),
    ("Comfy-Org/MiniMax-H3", "vae/minimax_h3_audio_vae_fp32.safetensors", "H3"),
    ("dseditor/minimax-h3-studio-assets", "loras/H3_Combat_V2.safetensors", "H3"),
    ("dseditor/minimax-h3-studio-assets", "loras/Motion_Repair.safetensors", "H3"),
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
    p.add_argument("--models-root", default=r"F:\AI\BANANAMV_27B_STUDIO\Models")
    args = p.parse_args()
    download_all(args.models_root)
