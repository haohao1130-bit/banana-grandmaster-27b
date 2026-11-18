"""Standalone, localhost-only Gemma 3 12B IT Q5_K_M GGUF director worker.

Owns only the llama-server process it spawned. The worker survives consecutive
clip-local rewrite retries, then must be stopped before ComfyUI H3 sampling.
No remote inference / no switch to the 9B rewriter in this branch.
"""
import base64
import io
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from urllib import error, request

_ROOT = Path(os.environ.get("BANANA_12B_ROOT", r"F:\BANANAMV_12B_STUDIO"))
DEFAULT_SERVER = _ROOT / "Runtime" / "llama.cpp" / "llama-server.exe"
DEFAULT_MODEL = _ROOT / "Models" / "12B" / "google_gemma-3-12b-it-Q5_K_M.gguf"
DEFAULT_MMPROJ = _ROOT / "Models" / "12B" / "mmproj-google_gemma-3-12b-it-f16.gguf"
_LOCK = threading.RLock()
_REQUEST_LOCK = threading.Lock()
_PROC = None
_CANCELLED = threading.Event()


def _gpu_layers(value):
    """Use 99 GPU layers as the full-offload target; allow custom caps."""
    if value is None or str(value).strip().lower() == "all":
        return 99
    if str(value).strip().lower() == "auto":
        return "auto"
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("12B gpu_layers must be 'auto' or a nonnegative integer") from exc
    if n < 0:
        raise ValueError("12B gpu_layers must be 'auto' or a nonnegative integer")
    return n


def _settings(cfg):
    rw = cfg.get("rewriter", {})
    host = "127.0.0.1"
    port = int(os.environ.get("BANANA_12B_PORT", rw.get("port", 8217)))
    if not 1025 <= port <= 65535:
        raise ValueError("12B localhost port invalid")
    return {
        "host": host, "port": port,
        "exe": Path(os.environ.get("BANANA_12B_SERVER") or rw.get("server") or DEFAULT_SERVER),
        "model": Path(os.environ.get("BANANA_12B_MODEL") or rw.get("model") or DEFAULT_MODEL),
        "mmproj": Path(os.environ.get("BANANA_12B_MMPROJ") or rw.get("mmproj") or DEFAULT_MMPROJ),
        "gpu_layers": _gpu_layers(rw.get("gpu_layers", 99)),
        "context": int(rw.get("context", 16384)),
        "max_tokens": int(rw.get("max_length", 8192)),
        "temperature": float(rw.get("temperature", 0.4)),
        "top_p": float(rw.get("top_p", 0.8)),
    }


def _url(s, endpoint):
    return "http://127.0.0.1:%d%s" % (s["port"], endpoint)


def _health(s, timeout=2):
    try:
        with request.urlopen(_url(s, "/health"), timeout=timeout) as resp:
            return json.load(resp).get("status") in ("ok", "no slot available")
    except (OSError, ValueError, error.URLError):
        return False


def _launch_args(s):
    # RTX 5070 12GB: prioritize language layers on CUDA; run Gemma 3 image
    # projector on CPU, because a multi-image burst can overflow VRAM.
    # Keep llama.cpp fit enabled for a safe first real-hardware smoke test.
    # Log real offload after load; 99 is the target, not a verified count.
    return [str(s["exe"]), "-m", str(s["model"]), "--mmproj", str(s["mmproj"]),
            "--host", s["host"], "--port", str(s["port"]),
            "-c", str(s["context"]), "-ngl", str(s["gpu_layers"]),
            "-fit", "on", "-fitt", "512", "-fa", "auto",
            "-ctk", "q8_0", "-ctv", "q8_0", "-np", "1", "-t", "8",
            "--no-mmproj-offload"]


def ensure_running(cfg):
    """Start our *own* local process; reject an occupied port we do not own."""
    global _PROC
    s = _settings(cfg)
    with _LOCK:
        if _PROC is not None and _PROC.poll() is None:
            if _health(s):
                return s
            raise RuntimeError("12B service process exists but is not responding")
        if _health(s):
            raise RuntimeError("12B port is already occupied by another process; refusing to take it over")
        for label in ("exe", "model", "mmproj"):
            if not s[label].is_file():
                raise FileNotFoundError("12B missing %s: %s; run one-click installer" % (label, s[label]))
        args = _launch_args(s)
        log = _ROOT / "Logs" / "gemma12b.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("ab") as output:
            banner = ("\n[BANANAMV Gemma 3 12B Q5] launch: "
                      "context=%s, gpu_layers=%s, fit=on, fitt=512MiB, "
                      "kv=q8_0, mmproj_offload=off, parallel=1\n"
                      % (s["context"], s["gpu_layers"]))
            output.write(banner.encode("utf-8"))
            output.flush()
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            _PROC = subprocess.Popen(args, cwd=str(s["exe"].parent),
                                     stdout=output, stderr=subprocess.STDOUT,
                                     creationflags=flags)
        _CANCELLED.clear()
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        if _CANCELLED.is_set():
            raise InterruptedError("12B director cancelled")
        with _LOCK:
            if _PROC is None or _PROC.poll() is not None:
                raise RuntimeError("12B llama-server exited during load; check Logs/gemma12b.log")
        if _health(s):
            return s
        time.sleep(2)
    stop()
    raise TimeoutError("12B did not become ready within 10 minutes; check gemma12b.log")


def _messages(system, parts):
    items = []
    for kind, value in parts:
        if kind == "text":
            items.append({"type": "text", "text": str(value)})
        elif kind == "image":
            # Preserve every actual image and ordering from the original 9B call.
            buf = io.BytesIO()
            value.convert("RGB").save(buf, format="JPEG", quality=88)
            uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
            items.append({"type": "image_url", "image_url": {"url": uri}})
        else:
            raise ValueError("Unknown director input part: " + str(kind))
    # Gemma 3 instruction template expects system guidance inside the user turn.
    # Preserve the exact picture order after the director's fixed instructions.
    instructions = {"type": "text", "text":
                    "[DIRECTOR SYSTEM INSTRUCTIONS]\n" + str(system) +
                    "\n[CURRENT CLIP COMMISSION]\n"}
    return [{"role": "user", "content": [instructions] + items}]


def _clean_output(value):
    # The renderer must never see internal reasoning or other model metadata.
    value = re.sub(r"<think>.*?</think>", "", str(value), flags=re.S | re.I)
    value = re.sub(r"^\s*<think>.*$", "", value, flags=re.S | re.I)
    return value.strip()


def generate(cfg, system, parts, job_id):
    """Compatible with existing rewrite(cfg, system, parts, job_id) interface."""
    with _REQUEST_LOCK:
        s = ensure_running(cfg)
        if _CANCELLED.is_set():
            raise InterruptedError("12B director cancelled")
        payload = {
            "model": s["model"].name,
            "messages": _messages(system, parts),
            "temperature": s["temperature"], "top_p": s["top_p"],
            "max_tokens": s["max_tokens"], "stream": False,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(_url(s, "/v1/chat/completions"), data=data,
                              headers={"Content-Type": "application/json"},
                              method="POST")
        try:
            with request.urlopen(req, timeout=1800) as response:
                answer = json.load(response)
        except error.HTTPError as exc:
            detail = exc.read(1200).decode("utf-8", "replace")
            raise RuntimeError("12B request failed: HTTP %s: %s" % (exc.code, detail)) from exc
        if _CANCELLED.is_set():
            raise InterruptedError("12B director cancelled")
        try:
            raw = answer["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("12B returned invalid chat completion") from exc
        if isinstance(raw, list):
            raw = "".join(str(part.get("text", "")) for part in raw if isinstance(part, dict))
        output = _clean_output(raw)
        if not output:
            raise ValueError("12B director returned empty text")
        return output


def stop(cancel=False):
    """Unload GPU memory by exiting only our own llama-server process."""
    global _PROC
    if cancel:
        _CANCELLED.set()
    with _LOCK:
        proc = _PROC
        _PROC = None
    if proc is None:
        return
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
    # GPU memory belongs to the OS process; wait for confirmed process exit.
    if proc.poll() is None:
        raise RuntimeError("12B process still alive; refuse to queue H3")
