"""Colab/local setup with a recoverable venv and visible, durable diagnostics."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run_logged(command, log_path):
    """Stream the actual failing command output and retain it locally."""
    with Path(log_path).open('a', encoding='utf-8') as log:
        label = '\n>>> ' + ' '.join(map(str, command)) + '\n'
        print(label, flush=True);log.write(label);log.flush()
        process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True,
                                   errors='replace', bufsize=1)
        for line in process.stdout:
            print(line, end='', flush=True);log.write(line);log.flush()
        process.stdout.close()
        code = process.wait()
        if code:
            raise RuntimeError(f'安裝步驟失敗（exit {code}）。完整輸出：{log_path}。'
                               '請以其中第一個 ERROR 為準，不由 Python 版本猜根因。')


def environment_info(python):
    try:
        result = subprocess.run([str(python), '-c',
            'import json,sys;print(json.dumps({"version":list(sys.version_info[:2]),'
            '"prefix":sys.prefix}))'], capture_output=True, text=True, timeout=15)
        return json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def prepare_environment(root=ROOT, base_python=sys.executable, runner=run_logged):
    root = Path(root)
    log = root/'setup.log'
    base = environment_info(base_python)
    if not base:
        raise RuntimeError('無法讀取目前 Python 資訊。')
    env = root/'.venv';python = env/'bin/python'
    current = environment_info(python)
    healthy = (current and current['version'] == base['version'] and
               Path(current['prefix']).resolve() == env.resolve())
    if env.exists() and not healthy:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        archived = root/('.venv-before-setup-'+stamp)
        env.rename(archived)
        print('保留無法沿用的環境：', archived, flush=True)
    if not healthy:
        # Avoid Debian/Colab ensurepip/apt dependencies. Bootstrap pip below with
        # the notebook interpreter's pip --python, into this venv only.
        runner([str(base_python), '-m', 'venv', '--without-pip',
                '--system-site-packages', str(env)], log)
    runner([str(base_python), '-m', 'pip', '--python', str(python), 'install',
            '--ignore-installed', 'pip>=25,<27'], log)
    runner([str(python), '-m', 'pip', '--version'], log)
    runner([str(python), '-m', 'pip', 'install', '-r', str(root/'requirements.txt')], log)
    runner([str(python), '-c',
            'import sys,gradio,huggingface_hub,PIL;'
            'print("Python:",sys.version,"Gradio:",gradio.__version__)'], log)
    return python


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    prepare_environment(args.root)
