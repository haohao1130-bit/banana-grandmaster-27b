"""Local UI; does not load or generate models until the user starts a pair."""
import argparse
import json
from pathlib import Path


def build_app(output_dir):
    import gradio as gr
    from PIL import Image,ImageOps
    from bench.tasks import preset
    from bench.runner import compare
    from bench.director_experiment import compare_directors, director_preset, retry_directors
    from bench.t8_adapter import DEFAULT_PATH
    def choose(mode,scope):return json.dumps(preset(mode,scope),ensure_ascii=False,indent=2)
    def run(mode,task,files,seed,tokens,order,progress=gr.Progress()):
        pictures=[]
        for file in files or []:
            with Image.open(file) as image:
                image=ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((768,768));pictures.append(image.copy())
        if len(pictures)>4:raise gr.Error('本測試台最多四張參考圖。')
        report,path=compare(mode,json.loads(task),pictures,{'seed':int(seed),'max_new_tokens':int(tokens),'order':order},output_dir,
                            progress=lambda text:progress(.5,desc=text))
        texts=[report['models'].get(label,{}).get('text') or json.dumps(report['models'].get(label,{}),ensure_ascii=False,indent=2) for label in ('9B','27B')]
        stats={label:{k:v for k,v in value.items() if k!='text'} for label,value in report['models'].items()}
        return *texts,stats,str(path)
    def run_director(brief,cues,files,model,seed,tokens,order,progress=gr.Progress()):
        pictures=[]
        for file in files or []:
            with Image.open(file) as image:
                image=ImageOps.exif_transpose(image).convert('RGB')
                image.thumbnail((768,768));pictures.append(image.copy())
        if len(pictures)>4:raise gr.Error('本測試台最多四張參考圖。')
        task=director_preset();task['brief']=brief
        task['local_vocal_cues']=json.loads(cues)
        report,path=compare_directors(task,pictures,{
            'model_label':model,'seed':int(seed),'max_new_tokens':int(tokens),'order':order},
            output_dir,DEFAULT_PATH,progress=lambda text:progress(.5,desc=text))
        return director_result(report,path)
    def director_result(report,path):
        texts=[report['arms'].get(arm,{}).get('text') or json.dumps(
            report['arms'].get(arm,report.get('setup_error',{})),ensure_ascii=False,indent=2)
            for arm in ('off','on')]
        summary={k:v for k,v in report.items() if k not in ('systems','payload','task','arms')}
        summary['arms']={arm:{k:v for k,v in value.items() if k!='text'}
                         for arm,value in report['arms'].items()}
        return *texts,summary,str(path)
    def retry_director(report_file,files,offline,progress=gr.Progress()):
        if not report_file:raise gr.Error('請先選擇先前下載的完整對照紀錄 JSON。')
        pictures=[]
        for file in files or []:
            with Image.open(file) as image:
                image=ImageOps.exif_transpose(image).convert('RGB')
                image.thumbnail((768,768));pictures.append(image.copy())
        report,path=retry_directors(report_file,pictures,output_dir,local_files_only=offline,
                                   progress=lambda text:progress(.5,desc=text))
        return director_result(report,path)
    with gr.Blocks(title='蕉宗 27B 大導演試煉場') as demo:
        gr.Markdown('# 🍌 蕉宗大導演試煉場\n官方 Qwen3.5 9B／27B，同任務、同 Seed、相同 NF4 量化，輪流載入。只測計畫與畫面描述，不生成影片。')
        gr.Markdown('這不是正式版 H3 專用改寫 9B 的直接對照。技術格式通過也不等於故事正確；請人工比較角色、因果、段落發展與結尾。')
        with gr.Accordion('新實驗：同一顆模型，T8 分鏡 Off／On',open=True):
            gr.Markdown('先測同一顆 27B 在精簡導演指令下，加入 T8 分鏡方法是否更會拍。'
                        '兩版共用故事、圖片、聲部分配和取樣設定，只改 T8 開關。'
                        '這是文字實驗；沒有生成影片，也不代表已接近 Seedance。')
            director_brief=gr.Textbox(value=director_preset()['brief'],lines=5,label='15 秒故事主軸與必要要求（其餘交給導演）')
            director_images=gr.File(file_count='multiple',file_types=['image'],label='這組實驗的參考圖（選填，最多四張）')
            gr.Markdown('有參考圖時，請在主軸寫明 Picture 1、Picture 2 各代表誰。兩版會看到同一組圖片。')
            with gr.Accordion('聲部時間與測試設定',open=False):
                cues=gr.Textbox(value=json.dumps(director_preset()['local_vocal_cues'],ensure_ascii=False,indent=2),
                                lines=8,label='本段聲部分配（使用者標註，JSON；無標註填 []）')
                model=gr.Dropdown(['27B','9B'],value='27B',label='兩版共同使用的通用模型')
                director_seed=gr.Number(value=42,precision=0,minimum=0,maximum=4294967295,label='共同 Seed')
                director_tokens=gr.Slider(512,8192,value=4096,step=512,label='每版輸出上限')
                director_order=gr.Dropdown(['Off first','On first'],value='Off first',label='執行順序（可反轉再測）')
            director_button=gr.Button('同一位導演，拍兩版比較',variant='primary')
            with gr.Row():
                off_text=gr.Textbox(label='精簡導演 · T8 Off',lines=22)
                on_text=gr.Textbox(label='精簡導演 · T8 On',lines=22)
            director_stats=gr.JSON(label='實驗設定、來源與執行結果')
            director_download=gr.File(label='完整輸入與原始輸出紀錄（JSON）')
            gr.Markdown('兩版依序執行，各自載入並釋放同一模型。首次下載與 NF4 量化可能很久；'
                        'T8 On 只使用固定版本的分鏡方法，未執行整套 T8 插件。')
            director_button.click(run_director,[director_brief,cues,director_images,model,director_seed,
                director_tokens,director_order],[off_text,on_text,director_stats,director_download],
                concurrency_limit=1,concurrency_id='bench_gpu')
            with gr.Accordion('失敗重試：保留成功稿，只補失敗的一版',open=False):
                retry_file=gr.File(file_types=['.json'],label='先前下載的完整對照紀錄 JSON')
                offline=gr.Checkbox(value=True,label='模型只讀已下載快取（缺檔時會報錯，可取消後重試）')
                gr.Markdown('沿用紀錄中的故事、指令、Seed 和模型 revision；上方圖片需與原測試相同。'
                            '成功稿不重跑，另存一份重試紀錄。')
                retry_button=gr.Button('只重試失敗稿')
                retry_button.click(retry_director,[retry_file,director_images,offline],
                    [off_text,on_text,director_stats,director_download],
                    concurrency_limit=1,concurrency_id='bench_gpu')
        gr.Markdown('## 原有實驗：通用 9B／27B 模型比較（較早 Banana 指令）')
        with gr.Row():
            mode=gr.Dropdown(['planner','writer'],value='planner',label='全曲規劃／單段畫面')
            scope=gr.Dropdown(['full','excerpt'],value='full',label='預設案例範圍（修改會重載案例）')
        task=gr.Textbox(value=choose('planner','full'),label='同一份任務 JSON（可修改）',lines=18)
        files=gr.File(file_count='multiple',file_types=['image'],label='參考圖（選填，最多四張；兩邊使用相同圖片）')
        with gr.Row():
            seed=gr.Number(value=42,precision=0,minimum=0,maximum=4294967295,label='Seed')
            tokens=gr.Slider(512,8192,value=4096,step=512,label='每模型輸出上限')
            order=gr.Dropdown(['9B first','27B first'],value='9B first',label='順序（可反轉再測）')
        button=gr.Button('請兩位導演各拍一版',variant='primary')
        with gr.Row():
            small=gr.Textbox(label='9B 原始輸出',lines=22)
            large=gr.Textbox(label='27B 原始輸出',lines=22)
        stats=gr.JSON(label='耗時、token、PyTorch 顯存與技術檢查')
        download=gr.File(label='下載完整對照紀錄（JSON）')
        gr.Markdown('第一次載入可能下載完整原始權重；NF4 是載入時量化，並不縮小下載檔。載入耗時含下載，不拿來當純推論速度。顯存數字只統計 PyTorch 配置；不含所有驅動及其他程序占用。換模型前會釋放上一顆。')
        mode.change(choose,[mode,scope],task);scope.change(choose,[mode,scope],task)
        button.click(run,[mode,task,files,seed,tokens,order],[small,large,stats,download],
                     concurrency_limit=1,concurrency_id='bench_gpu')
    return demo


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='runs');parser.add_argument('--port',type=int,default=7860)
    args=parser.parse_args();Path(args.output).mkdir(parents=True,exist_ok=True)
    build_app(args.output).queue(default_concurrency_limit=1).launch(server_name='127.0.0.1',server_port=args.port,
        share=False,allowed_paths=[str(Path(args.output).resolve())])
