"""Native H3 9B + pinned T8 storyboard experiment. Generic 27B UI retired."""
import argparse
from pathlib import Path
import gradio as gr
from bench.native9b import compare

ROOT = Path(__file__).resolve().parent

def build_app(output, runtime):
    with gr.Blocks(title='Banana H3 9B × T8') as demo:
        gr.Markdown('# Banana H3 專用 9B × T8\nOff＝原生 Ref2VA 系統＋官方指南；On＝相同輸入，另加一次 T8 分鏡指令。只產生文字。\n9B 未直接聽音訊；歌詞、情緒與分秒由你提供。27B 已停用。')
        brief = gr.Textbox(label='故事、角色對應、片長、情緒與必要約束', lines=12,
            value='15-second music-video sequence. Reference 1 is the male musician; Reference 2 is the female service agent. Intercut his dark cluttered studio with her sterile white call center. He completes a project; she remotely applies a final modification; his work vanishes; blank paper floods his desk. His frustration erupts while she remains professionally pleasant. Design the performance, camera and edit. Preserve reference identity; expressions and poses may change. Preserve this event causality. No spoken dialogue. Use the original song: <Audio 1>: fully_copy. Musical mood supplied by user: furious dark rock; this is context, not measured vocal intensity.')
        images = gr.File(label='依序上傳參考圖（最多四張）', file_count='multiple', type='filepath', file_types=['image'])
        with gr.Row():
            seed = gr.Number(label='Seed', value=42, precision=0)
            length = gr.Slider(512, 16384, value=8192, step=512, label='最大輸出長度')
            order = gr.Radio(['Off first','On first'], value='Off first', label='執行順序')
        run = gr.Button('執行原生 9B Off / On', variant='primary')
        status = gr.Markdown()
        with gr.Row():
            off = gr.Textbox(label='Off 原始輸出', lines=24)
            on = gr.Textbox(label='On 原始輸出', lines=24)
        download = gr.File(label='完整報告（原始輸出／來源／設定）')
        def execute(brief, images, seed, length, order, progress=gr.Progress()):
            report, path = compare(brief, images or [], output, runtime, seed, length, order,
                                   progress=lambda s: progress(0, desc=s))
            def display(arm):
                value = report['arms'].get(arm, {})
                return value.get('text') or value.get('error') or '前一組失敗，未提交此組。'
            ok = len(report['arms']) == 2 and all(v['status']=='ok' for v in report['arms'].values())
            return ('兩組文字完成；尚未驗證影片效果。' if ok else '執行未完成，錯誤與已完成結果已保存。'), display('off'), display('on'), path
        run.click(execute, [brief, images, seed, length, order], [status, off, on, download], concurrency_limit=1)
    return demo

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'runs')
    parser.add_argument('--runtime', type=Path, default=ROOT/'runtime/native9b')
    parser.add_argument('--port', type=int, default=7860)
    args = parser.parse_args()
    build_app(args.output, args.runtime).queue().launch(server_name='127.0.0.1',server_port=args.port,share=False)
