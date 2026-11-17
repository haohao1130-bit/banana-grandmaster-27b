# RTX 5070 / 12 GB: 9B -> 27B Q4_K_M migration research (2026-11-18)

Status: **design only, not GPU-verified**. Nothing in this document changes the default 9B path. Work only on `experiment/rtx5070-latest-27b-lab`.

## Verified baseline

- Target source: `haohao1130-bit/banana-mv-public`, `experiment/rtx5070-480p-local`, `0efc0cf40e03140332d642e83159a413e42e4fa6`.
- Target repository branch synchronized at `6ce57092d505e30e4872bedd6353139b986a1926`.
- Its Git tree SHA is `f59f719c68c615b01d54cb27f8abd54a579fc088`, **identical** to the source branch tree. No source drift after synchronization.
- The `banana-grandmaster-27b/main` branch, existing ComfyUI/H3 install, production 9B and Colab entrypoints were not changed.
- This is a software source update only, not proof of GPU runtime success.

## What the current code REALLY does

- `banana_mv/services.py` defaults to MiniMax H3-specific `minimax_h3_rewriter_ref2va_qwen3.5_9b_w4a8.safetensors`.
- `build_rewrite_graph()` calls ComfyUI `CLIPLoader` -> `TextGenerate` -> `PreviewAny`; the `parts` list contains both **text and PIL images**, not only text.
- `rewrite_local()` submits the Comfy prompt, waits, and optionally POSTs `/free` after success. This affects **ComfyUI-owned models only**; it cannot unload an independent Ollama/llama.cpp worker.
- `banana_mv/server.py` has hard-coded `CLIPLoader` / `TextGenerate` preflight for plan review/director modes (~lines 927-934), which must become backend-aware.
- `active_rewrite_prompt_id()` and emergency-stop integration currently assume ComfyUI prompt IDs; an external backend requires cancellation support and a separately tracked process/request.
- `locked_shoot.py` and `director_shoot.py` both call the same `rewrite(cfg, system, parts, job_id)` interface. Preserve the interface and Python-owned SRT, role, wardrobe and single-clip boundaries.

## Model choice and memory

Research target: **Qwen3.5-27B GGUF Q4_K_M** as a plausible successor to the Qwen3.5 9B rewriter. *The exact GGUF publisher and file have not yet been selected.* Q4_K_M artifacts differ by publisher; current listings show around 16.7-18.0 GB, plus approximately 0.93 GB `mmproj` for image support. These are download sizes, not a guarantee of in-use GPU memory. With 12 GB VRAM, plan for partial GPU offload and system RAM. The user's 64 GB RAM is suitable for a trial but paging/VRAM pressure may still make it slow.

The 9B is H3 Ref2VA-specialized; a general 27B is **not automatically a drop-in format improvement**. Keep the H3 native six-section output contract, image/subject references and structured validation. Test actual quality before relaxing creative restrictions.

Never hard-code “28-32 GPU layers”. Layer weights, mmproj, KV cache, context size, driver and other GPU processes affect headroom. Start with shorter context (e.g. 4096), safe VRAM headroom, use `--fit on`/`--fit-target` if supported by the installed llama.cpp version, and tune offload based on observed peak memory. The initial `-ngl 20` example below is **a trial value, not a validated configuration**.

## Proposed runtime: separate, ephemeral llama.cpp service

Prefer a `llama-server` worker for experimental GGUF + vision routing. It can receive the same multi-image `parts` as typed OpenAI-compatible image URL / text blocks. This requires a **matching mmproj**; a text-only call would regress the current image-aware rewriter.

Example *manual smoke test only* (replace paths with actual model/projector; needs a supported CUDA llama.cpp build):

```powershell
& "PATH_TO_LLAMA_SERVER\llama-server.exe" `
  -m "PATH_TO_27B\Qwen3.5-27B-Q4_K_M.gguf" `
  --mmproj "PATH_TO_27B\mmproj-F16.gguf" `
  --host 127.0.0.1 --port 8217 `
  -c 4096 -ngl 20 --fit on --fit-target 1536 --no-mmproj-offload
```

When integrating: use localhost only; do not accept arbitrary external URLs in user/model config. Set explicit request deadlines and preserve the order of text + image parts. No paid API or remote data transmission.

### Lifetime / VRAM hand-off

- Before each rewrite phase: if GPU budget is tight, ensure ComfyUI has unloaded idle *H3* models and is not rendering. Wait for the 27B worker ready endpoint.
- Generate *all retries/repairs for the current phase* under one 27B process. Do **not** restart a ~17 GB model between every repair call.
- After the rewrite phase, stop the 27B **owned worker**, wait for its process exit and observe GPU memory recovery **before submitting the H3 Comfy prompt**. Avoid terminating user-launched llama-server processes.
- In the existing chain/last-frame pipeline the next clip may require a previously rendered frame as an image reference, so naively prewriting every clip before rendering can break behavior. An alternative CPU-only resident worker (0 GPU layers) trades speed for no GPU residency conflicts; benchmark separately.
- `torch.cuda.empty_cache()` alone only addresses unused blocks in the *calling PyTorch process*, not VRAM owned by another process. `/free` on ComfyUI alone does not close llama.cpp.
- Ollama could instead use `keep_alive: 0` for unloading after the request. If chosen, verify model+mmproj vision, complete response and released VRAM before H3. This is a different backend, not a ComfyUI setting.

## Minimal source patch plan (new opt-in only)

1. `services.py`: add explicitly selected backend (`comfy9b` default, `llama27b` opt-in). Preserve the `rewrite_local(cfg, system, parts, job_id)` signature; route to provider. Adapt system/user text and ordered images to OpenAI-compatible content blocks. Do **not** inject the 9B's manual ChatML and `<think>` tags into the 27B API; let the model's real chat template apply.
2. Add a 27B worker controller module that starts/owns/stops the local process, handles health checks, timeouts, serialization, cancellation and idempotent cleanup. Never `taskkill` all llama-server processes.
3. `server.py`: preflight the selected provider rather than requiring `TextGenerate` for all director paths; retain H3 Comfy graph preflight, GPU_LOCK and emergency-stop behavior.
4. `tools/start_classic_local.ps1`: preserve CUDA13 and ComfyUI 9B defaults; add an **explicit separate 27B shortcut/config** after tests. Do not silently download models, overwrite config or switch the working 9B instance.
5. H3 contract tests and A/B prompts: identical clip schedules, SRT/image identity, picture count, explicit vocal role, no past/future plot leak, multi-image referencing, framing, directional camera commands, tail-frame handoff; measure response latency, retries and VRAM.

## Acceptance checklist (hardware required)

- [ ] Source tree and original 9B regression tests remain unchanged.
- [ ] 27B worker can ingest *two distinct reference images* plus the current clip's text without any role/image swaps.
- [ ] The complete H3 native prompt passes all existing parsers/validators and respects explicit S1/S2 vocal windows.
- [ ] Repeated prompts do not introduce past/future event leakage; arbitrary `<think>` content is not forwarded to H3.
- [ ] Automatic/manual cancel terminates only owned 27B job/process and releases GPU memory.
- [ ] 27B exits and GPU memory recovers before H3 queue submit, including error/retry/cancel paths.
- [ ] RTX 5070 runs a fresh 5-second test, then two linked clips, then a longer test; compare against the exact 9B baseline.
- [ ] 9B default + old saved projects still work; no frontend or existing launcher regression.

## External references (reviewed 2026-11-18)

- Qwen3.5-27B GGUF artifact & projector examples: https://huggingface.co/unsloth/Qwen3.5-27B-GGUF
- Alternative model/size listing: https://huggingface.co/bartowski/Qwen_Qwen3.5-27B-GGUF
- llama.cpp server options, image payloads, offload and fit behavior: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- Ollama unload API: https://github.com/ollama/ollama/blob/main/docs/api.md
