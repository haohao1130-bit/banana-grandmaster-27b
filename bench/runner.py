"""Sequential paired inference. Heavy GPU libraries are imported only when run."""
import gc
import hashlib
import json
import platform
import time
import uuid
from datetime import datetime,timezone
from pathlib import Path

MODELS={'9B':'Qwen/Qwen3.5-9B','27B':'Qwen/Qwen3.5-27B'}


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)


class HFBackend:
    def run(self,label,system,task,images,settings):
        import torch
        import transformers
        from huggingface_hub import HfApi
        from transformers import AutoProcessor, AutoModelForImageTextToText, BitsAndBytesConfig, set_seed
        if not torch.cuda.is_available():raise RuntimeError('請選擇 Colab GPU；此測試不會偷偷改用 CPU。')
        model_id=MODELS[label];revision=settings.get('model_revision') or HfApi().model_info(model_id).sha
        model=processor=inputs=generated=None
        dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        content=[{'type':'text','text':task}]
        for i,picture in enumerate(images,1):
            content.extend([{'type':'text','text':f'Original reference {i}:'},{'type':'image','image':picture}])
        messages=[{'role':'system','content':system},{'role':'user','content':content}]
        try:
            torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats();start=time.perf_counter()
            quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=dtype)
            processor=AutoProcessor.from_pretrained(model_id,revision=revision,trust_remote_code=False)
            model=AutoModelForImageTextToText.from_pretrained(model_id,revision=revision,
                quantization_config=quant,device_map={'':'cuda:0'},dtype=dtype,attn_implementation='sdpa',trust_remote_code=False)
            model.eval();torch.cuda.synchronize();load_seconds=time.perf_counter()-start
            load_peak=torch.cuda.max_memory_allocated()
            inputs=processor.apply_chat_template(messages,tokenize=True,return_dict=True,
                return_tensors='pt',add_generation_prompt=True,enable_thinking=False).to('cuda:0')
            if inputs['input_ids'].shape[1]>16384:raise ValueError('測試輸入超過 16384 tokens，請縮短任務或減少圖片。')
            set_seed(settings['seed']);torch.cuda.synchronize();torch.cuda.reset_peak_memory_stats();start=time.perf_counter()
            with torch.inference_mode():
                generated=model.generate(**inputs,max_new_tokens=settings['max_new_tokens'],do_sample=True,
                    temperature=.7,top_p=.8,top_k=20,repetition_penalty=1.0)
            torch.cuda.synchronize();elapsed=time.perf_counter()-start
            token_ids=generated[0,inputs['input_ids'].shape[1]:].tolist()
            output=processor.decode(token_ids,skip_special_tokens=True)
            eos=model.generation_config.eos_token_id;eos=eos if isinstance(eos,list) else [eos]
            return {'status':'ok','text':output,'model':model_id,'revision':revision,
                'runtime':{'python':platform.python_version(),'torch':torch.__version__,'transformers':transformers.__version__,
                           'gpu':torch.cuda.get_device_name(0),'quantization':'bitsandbytes NF4 double quant','compute_dtype':str(dtype),'attention':'sdpa','cpu_offload':False},
                'metrics':{'load_seconds_including_download':load_seconds,'generation_seconds':elapsed,
                    'input_tokens':inputs['input_ids'].shape[1],'output_tokens':len(token_ids),
                    'output_tokens_per_second':len(token_ids)/elapsed if elapsed else None,
                    'load_peak_torch_allocated_bytes':load_peak,
                    'generation_peak_torch_allocated_bytes':torch.cuda.max_memory_allocated(),
                    'generation_peak_torch_reserved_bytes':torch.cuda.max_memory_reserved(),
                    'hit_token_budget':len(token_ids)>=settings['max_new_tokens'] and bool(token_ids) and token_ids[-1] not in eos}}
        finally:
            generated=inputs=processor=model=None;gc.collect();torch.cuda.empty_cache()


def compare(mode,task,images,settings,output_dir,backend=None,progress=None):
    from bench.tasks import system_for,technical_check
    if mode not in ('planner','writer'):raise ValueError('未知測試類型。')
    if not isinstance(task,dict):raise ValueError('任務 JSON 必須是物件。')
    if not 0<=int(settings['seed'])<2**32:raise ValueError('Seed 需為 0–4294967295。')
    if not 1<=int(settings['max_new_tokens'])<=8192:raise ValueError('輸出上限需為 1–8192 tokens。')
    settings=dict(settings,seed=int(settings['seed']),max_new_tokens=int(settings['max_new_tokens']),
                  temperature=.7,top_p=.8,top_k=20,thinking=False,repetition_penalty=1.0)
    order=['9B','27B'] if settings.get('order','9B first')=='9B first' else ['27B','9B']
    system=system_for(mode,task);payload=json.dumps(task,ensure_ascii=False)
    backend=backend or HFBackend();run_id=time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
    path=Path(output_dir)/f'{run_id}.json'
    # Hash image pixels after the same thumbnail/EXIF normalization used by the UI.
    report={'id':run_id,'created_at_utc':datetime.now(timezone.utc).isoformat(),
            'mode':mode,'task':task,'system':system,'settings':settings,'order':order,
            'image_sha256':[hashlib.sha256(p.tobytes()).hexdigest() for p in images],
            'image_sizes':[list(p.size) for p in images],
            'scope':'Official generic Qwen3.5 model comparison; NOT the specialized MiniMax H3 9B rewriter.',
            'models':{},'visual_verified':False}
    atomic_json(path,report)
    for label in order:
        if progress:progress('Loading / running '+label)
        try:
            result=backend.run(label,system,payload,images,settings)
            result['technical_check']=technical_check(mode,result['text'],task,len(images))
        except Exception as error:
            result={'status':'error','model':MODELS[label],'error_type':type(error).__name__,'error':str(error)}
        report['models'][label]=result;atomic_json(path,report)
        if progress:progress(label+' completed: '+result['status'])
    return report,path
