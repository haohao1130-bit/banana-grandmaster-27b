"""Build a clean standalone Colab, with no model execution on install."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def cell(kind,text):
    result={'cell_type':kind,'metadata':{},'source':text.splitlines(keepends=True)}
    if kind=='code':result.update(execution_count=None,outputs=[])
    return result


def build(source_ref='main',filename='Banana_Grandmaster_27B.ipynb'):
    cells=[cell('markdown','''# 🍌 蕉宗 27B 大導演試煉場
獨立測試，不修改正式 Banana MV。官方 Qwen3.5 9B 與 27B 使用相同任務、NF4 量化、Seed 和取樣參數，逐顆載入。

這不是 H3 專用改寫 9B 的直接對照；先測參數規模與故事指令表現。只生成文字，沒有影片／原曲下載。

預設 GPU 偏好為 G4。請在「執行階段 → 變更執行階段類型」確認選擇 G4；實際分配依 Colab 資源與帳戶而定。程式不自動切成 CPU 或更低精度。原始權重下載可能約數十 GB；4-bit 只在載入時量化。'''),
    cell('code','''# ① 下載獨立程式，使用自己的虛擬環境（沿用 Colab 的 PyTorch）
import subprocess, sys
from pathlib import Path
ROOT=Path('/content/banana-grandmaster-27b')
SOURCE_REF = 'BENCH_SOURCE_REF' # @param {type:"string"}
if not ROOT.exists():
    subprocess.run(['git','clone','--branch',SOURCE_REF,'https://github.com/haohao1130-bit/banana-grandmaster-27b.git',str(ROOT)],check=True)
else:
    actual_ref=subprocess.check_output(['git','-C',str(ROOT),'branch','--show-current'],text=True).strip()
    if actual_ref!=SOURCE_REF:
        raise RuntimeError('目前 checkout 是 '+actual_ref+'，本筆記本要求 '+SOURCE_REF+'。請換乾淨執行階段，或停止服務後手動切換；不自動覆寫舊程式。')
    print('沿用目前分支；需要新版時先停止服務再更新。')
print('目前程式提交：',subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip())
PY=ROOT/'.venv/bin/python'
if not PY.exists():
    subprocess.run([sys.executable,'-m','venv','--system-site-packages',str(ROOT/'.venv')],check=True)
subprocess.run([str(PY),'-m','pip','install','-q','-r',str(ROOT/'requirements.txt')],check=True)
subprocess.run([str(PY),str(ROOT/'tools/fetch_t8.py')],check=True)
print('程式、套件與固定 T8 分鏡來源就位。尚未下載權重或執行模型。')'''),
    cell('code','''# ② 選擇是否保存測試結果與模型快取到 Drive
SAVE_TO_DRIVE = True # @param {type:"boolean"}
import os
env=dict(os.environ)
if SAVE_TO_DRIVE:
    from google.colab import drive
    drive.mount('/content/drive')
    DATA=Path('/content/drive/MyDrive/BananaGrandmaster27B')
else:
    DATA=ROOT/'local_data'
DATA.mkdir(parents=True,exist_ok=True)
env['HF_HOME']=str(DATA/'cache')
OUTPUT=DATA/'runs'
print('結果位置：',OUTPUT)
print('兩顆模型都會在按下測試後才下載／載入。')'''),
    cell('code','''# ③ 啟動內嵌測試介面；按介面按鈕才跑模型
import time, urllib.request
from google.colab import output
LOG=ROOT/'bench.log'
if 'bench_process' not in globals() or bench_process.poll() is not None:
    bench_log=LOG.open('a')
    bench_process=subprocess.Popen([str(PY),str(ROOT/'app.py'),'--output',str(OUTPUT),'--port','7860'],cwd=ROOT,env=env,stdout=bench_log,stderr=subprocess.STDOUT)
deadline=time.monotonic()+90
while time.monotonic()<deadline:
    if bench_process.poll() is not None:raise RuntimeError(LOG.read_text()[-6000:])
    try:
        urllib.request.urlopen('http://127.0.0.1:7860/',timeout=3).close()
        break
    except OSError:time.sleep(1)
else:raise RuntimeError('啟動尚未完成，請查看 '+str(LOG))
output.serve_kernel_port_as_iframe(7860,height=1000)'''),
    cell('code','''# 手動停止按鈕：全部執行只顯示按鈕，不會關閉服務
import ipywidgets as widgets
from IPython.display import display
stop_button=widgets.Button(description='停止試煉服務',button_style='warning')
stop_output=widgets.Output()
def stop_owned_process(_):
    with stop_output:
        stop_output.clear_output()
        if 'bench_process' not in globals() or bench_process.poll() is not None:
            print('服務已停止。');return
        bench_process.terminate()
        try:bench_process.wait(timeout=10)
        except subprocess.TimeoutExpired:bench_process.kill();bench_process.wait()
        print('試煉服務已停止；已存結果保留。Colab 的 GPU 配置仍需在執行階段選單自行結束。')
stop_button.on_click(stop_owned_process)
display(stop_button,stop_output)''')]
    notebook={'cells':cells,'metadata':{'accelerator':'GPU','colab':{'name':'Banana_Grandmaster_27B.ipynb','gpuType':'G4'},
               'kernelspec':{'display_name':'Python 3','name':'python3'}},'nbformat':4,'nbformat_minor':5}
    notebook['metadata']['colab']['name']=filename
    for item in notebook['cells']:
        item['source']=[line.replace('BENCH_SOURCE_REF',source_ref) for line in item['source']]
    (ROOT/filename).write_text(json.dumps(notebook,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    build()
    build('experiment/t8-director-ab','Banana_T8_Director_AB.ipynb')
