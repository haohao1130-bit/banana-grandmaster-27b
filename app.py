"""Local UI; does not load or generate models until the user starts a pair."""
import argparse
import json
from pathlib import Path


def build_app(output_dir):
    import gradio as gr
    from PIL import Image,ImageOps
    from bench.tasks import preset
    from bench.runner import compare
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
    with gr.Blocks(title='蕉宗 27B 大導演試煉場') as demo:
        gr.Markdown('# 🍌 蕉宗大導演試煉場\n官方 Qwen3.5 9B／27B，同任務、同 Seed、相同 NF4 量化，輪流載入。只測計畫與畫面描述，不生成影片。')
        gr.Markdown('這不是正式版 H3 專用改寫 9B 的直接對照。技術格式通過也不等於故事正確；請人工比較角色、因果、段落發展與結尾。')
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
        button.click(run,[mode,task,files,seed,tokens,order],[small,large,stats,download],concurrency_limit=1)
    return demo


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='runs');parser.add_argument('--port',type=int,default=7860)
    args=parser.parse_args();Path(args.output).mkdir(parents=True,exist_ok=True)
    build_app(args.output).queue(default_concurrency_limit=1).launch(server_name='127.0.0.1',server_port=args.port,
        share=False,allowed_paths=[str(Path(args.output).resolve())])
