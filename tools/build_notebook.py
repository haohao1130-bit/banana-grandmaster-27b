"""Build isolated native 9B Colab; old notebook URLs use this same entrypoint."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REF='experiment/t8-director-ab'

def cell(kind, text):
    result={'cell_type':kind,'metadata':{},'source':text.splitlines(keepends=True)}
    if kind=='code': result.update(execution_count=None,outputs=[])
    return result

SETUP='''# ① 安裝介面（不下載 27B）
import subprocess, sys, os, time, urllib.request
from pathlib import Path
ROOT=Path('/content/banana-grandmaster-27b')
SOURCE_REF = 'experiment/t8-director-ab'
for owned_name in ('bench_process','native_process'):
    owned=globals().get(owned_name)
    if owned is not None and owned.poll() is None:
        raise RuntimeError('請先按最後一格的停止按鈕，再更新。')
if not ROOT.exists():
    subprocess.run(['git','clone','--branch',SOURCE_REF,'https://github.com/haohao1130-bit/banana-grandmaster-27b.git',str(ROOT)],check=True)
else:
    actual_ref=subprocess.check_output(['git','-C',str(ROOT),'branch','--show-current'],text=True).strip()
    if actual_ref!=SOURCE_REF: raise RuntimeError('分支不同；請使用新的執行階段。')
    if subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain'],text=True).strip():
        raise RuntimeError('有本地變更；請先保留，不自動覆寫。')
    subprocess.run(['git','-C',str(ROOT),'pull','--ff-only','origin',SOURCE_REF],check=True)
print('提交：',subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip())
subprocess.run([sys.executable,str(ROOT/'tools/setup_environment.py')],check=True)
PY=ROOT/'.venv/bin/python'
subprocess.run([str(PY),str(ROOT/'tools/fetch_t8.py')],check=True)
'''
DATA='''# ② Drive 只保存結果；權重與 HF 快取放在 Colab 本機
SAVE_TO_DRIVE=True # @param {type:"boolean"}
if SAVE_TO_DRIVE:
    from google.colab import drive
    drive.mount('/content/drive')
    OUTPUT=Path('/content/drive/MyDrive/Banana9BT8Bench/runs')
else: OUTPUT=ROOT/'runs'
OUTPUT.mkdir(parents=True,exist_ok=True)
env=dict(os.environ)
env['HF_HOME']=str(ROOT/'cache/hf-native9b')
env['HF_HUB_DISABLE_SHARED_BLOBS']='1'
env['HF_HUB_DISABLE_SYMLINKS']='1'
print('結果：',OUTPUT)
'''
START='''# ③ 準備 H3 專用 9B，啟動獨立 Comfy（8189）與測試介面（7860）
# 首次下載只有 9B 改寫模型，沒有 H3 影片模型。下載進度會顯示。
if any(globals().get(n) is not None and globals()[n].poll() is None for n in ('native_process','bench_process')):
    raise RuntimeError('服務仍執行；請先按停止按鈕。')
def port_busy(port):
    import socket
    with socket.socket() as sock: return sock.connect_ex(('127.0.0.1',port))==0
if port_busy(8189) or port_busy(7860): raise RuntimeError('8189 或 7860 已被使用；不接管既有服務。')
subprocess.run([str(PY),str(ROOT/'tools/native9b_runtime.py')],cwd=ROOT,env=env,check=True)
RUNTIME=ROOT/'runtime/native9b'
def launch(command, log_name):
    with (ROOT/log_name).open('a') as log:
        return subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
def ready(process, url, log_name, timeout=180):
    deadline=time.monotonic()+timeout
    last_heartbeat=0
    while time.monotonic()<deadline:
        if process.poll() is not None: raise RuntimeError((ROOT/log_name).read_text()[-8000:])
        try:
            urllib.request.urlopen(url,timeout=3).close();return
        except OSError: pass
        if time.monotonic()-last_heartbeat>15:
            print('等待服務啟動；日誌：',ROOT/log_name,flush=True);last_heartbeat=time.monotonic()
        time.sleep(1)
    raise RuntimeError('啟動超時，請查看 '+str(ROOT/log_name)+'；停止後再重試。')
native_process=launch([str(PY),str(RUNTIME/'ComfyUI/main.py'),'--listen','127.0.0.1','--port','8189','--disable-all-custom-nodes'],'native9b.log')
ready(native_process,'http://127.0.0.1:8189/object_info','native9b.log')
bench_process=launch([str(PY),str(ROOT/'app.py'),'--output',str(OUTPUT),'--port','7860'],'bench.log')
ready(bench_process,'http://127.0.0.1:7860/','bench.log')
from google.colab import output
output.serve_kernel_port_as_iframe(7860,height=1100)
'''
STOP='''# ④ 手動停止兩個實驗服務；全部執行只顯示按鈕
import ipywidgets as widgets
from IPython.display import display
button=widgets.Button(description='停止 9B 實驗服務',button_style='warning')
messages=widgets.Output()
def stop(_):
    with messages:
        messages.clear_output()
        for name in ('bench_process','native_process'):
            process=globals().get(name)
            if process is not None and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill();process.wait()
        print('實驗服務已停止；結果與既有 27B 檔案保留。')
button.on_click(stop)
display(button,messages)
'''

def build(filename):
    cells=[cell('markdown', '''# Banana H3 專用 9B × T8
27B 已停用。獨立文字實驗，不修改正式 BananaMV，不執行 H3 影片生成。

Off：原生 Ref2VA 系統＋官方指南。On：相同 9B、故事、圖片、Seed 與取樣，另加固定版本的 T8 分鏡指令一次；不是完整 T8 enhancer。

GPU 偏好 G4，請確認執行階段類型。首次下載 9B 仍需時間與本機磁碟；新執行階段需要重新下載。Drive 只保存報告，不沿用失敗的 27B tokenizer 快取。''')]
    cells += [cell('code',s) for s in (SETUP,DATA,START,STOP)]
    notebook={'cells':cells,'metadata':{'accelerator':'GPU','colab':{'name':filename,'gpuType':'G4'},'kernelspec':{'display_name':'Python 3','name':'python3'}},'nbformat':4,'nbformat_minor':5}
    (ROOT/filename).write_text(json.dumps(notebook,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    for name in ('Banana_9B_T8_AB.ipynb','Banana_T8_Director_AB.ipynb','Banana_Grandmaster_27B.ipynb'): build(name)
