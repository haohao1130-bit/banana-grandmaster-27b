"""Local-only restart supervisor for the independent BANANAMV 27B backend.

It only owns the Python HTTP child process it starts. It cannot terminate a
different 8193 listener, ComfyUI, BANANAFILM or another studio. Models, jobs,
and finished clips are stored outside the application process and survive it.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib import request


APP = Path(__file__).resolve().parents[1]
DATA = Path(os.environ["BANANA_DATA"]).resolve()
HEARTBEAT = DATA / "restart-controller.heartbeat"
REQUEST = DATA / "restart-request.json"
BRANCH = "experiment/rtx5070-latest-27b-lab"
HEALTH = "http://127.0.0.1:8193/api/health"


def current_instance(expected_pid):
    try:
        with request.urlopen(HEALTH, timeout=2) as response:
            payload = json.load(response)
        if payload.get("standalone") and payload.get("pid") == expected_pid:
            return payload.get("instance")
        return None
    except (OSError, ValueError):
        return None


def try_update_source():
    """Safe ff-only update while our HTTP child is offline; no force/reset."""
    try:
        origin = subprocess.run(
            ["git", "-C", str(APP), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        if "haohao1130-bit/banana-grandmaster-27b" not in origin.lower():
            print("27B supervisor: unexpected Git remote; skipping update.", flush=True)
            return
        branch = subprocess.run(
            ["git", "-C", str(APP), "branch", "--show-current"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        if branch != BRANCH:
            print("27B supervisor: non-lab branch; skipping update.", flush=True)
            return
        dirty = subprocess.run(
            ["git", "-C", str(APP), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        if dirty:
            print("27B supervisor: local source edits; retaining checkout.", flush=True)
            return
        subprocess.run(
            ["git", "-C", str(APP), "pull", "--ff-only", "origin", BRANCH],
            timeout=90, check=True,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        print("27B supervisor: source update skipped:", exc, flush=True)


def start_http():
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "banana_mv.server"],
        cwd=str(APP),
        env=os.environ.copy(),
    )
    # Only the process that opened 8193 should be controlled. Verify its
    # health before accepting browser restart requests.
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("27B HTTP backend exited at startup (code %s)" % proc.returncode)
        instance = current_instance(proc.pid)
        if instance:
            print("27B supervisor: backend ready, instance", instance, flush=True)
            return proc, instance
        HEARTBEAT.touch()
        time.sleep(2)
    proc.terminate()
    proc.wait(timeout=20)
    raise RuntimeError("27B backend did not start on 8193; check port/logs")


def valid_request(payload, instance):
    if not isinstance(payload, dict):
        return False
    issued = payload.get("issued_at")
    if (payload.get("version") != 1
            or payload.get("instance") != instance
            or not isinstance(issued, (int, float))):
        return False
    return 0 <= time.time() - issued <= 45


def run():
    DATA.mkdir(parents=True, exist_ok=True)
    REQUEST.unlink(missing_ok=True)   # stale request from an earlier crash
    HEARTBEAT.touch()
    proc = None
    try:
        proc, instance = start_http()
        while True:
            if proc.poll() is not None:
                raise RuntimeError("27B backend exited unexpectedly (code %s)" % proc.returncode)
            HEARTBEAT.touch()
            if REQUEST.is_file():
                processing = DATA / "restart-request.processing"
                try:
                    REQUEST.replace(processing)
                    payload = json.loads(processing.read_text(encoding="utf-8"))
                    # The requested instance must match the backend we OWN
                    # and the current live health endpoint.
                    if valid_request(payload, instance) and current_instance(proc.pid) == instance:
                        print("27B supervisor: confirmed idle restart, recycling owned HTTP backend.", flush=True)
                        proc.terminate()
                        try:
                            proc.wait(timeout=20)
                        except subprocess.TimeoutExpired:
                            # Only the exact subprocess handle we launched.
                            proc.kill()
                            proc.wait(timeout=10)
                        proc = None
                        try_update_source()
                        proc, instance = start_http()
                    else:
                        print("27B supervisor: ignored stale/invalid restart request.", flush=True)
                except (OSError, ValueError) as exc:
                    print("27B supervisor: invalid restart request:", exc, flush=True)
                finally:
                    processing.unlink(missing_ok=True)
            time.sleep(2)
    finally:
        HEARTBEAT.unlink(missing_ok=True)
        REQUEST.unlink(missing_ok=True)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("27B supervisor stopped by operator.", flush=True)
    except Exception as exc:
        print("27B supervisor failed:", exc, file=sys.stderr, flush=True)
        sys.exit(1)
