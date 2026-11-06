"""Small reproducible fixtures and technical checks, never a story-quality judge."""
import json
import math
import re


def preset(mode='planner',scope='full'):
    if mode=='writer':
        return {'visual_task':'On the boxing ring, the non-singing mascot slips one punch and counters. The opponent recoils; the contest remains unresolved.',
            'seconds':10,'appearance_start':{'characters':{
                'S2':{'connected_reference':None,'location':'arena','wearing':[], 'held_props':[]}},
                'environments':{'arena':{'active_location':'boxing ring'}}},
            'reference_mapping':{},'previous_last_frame':None,
            'constraints':['S2 never sings. The singer remains on a separate concert stage; do not bring the singer into this clip.'],
            'cinematography':'One readable attack, evasion, short counter, contact and recoil. One motivated camera move; brief speed contrast, no constant whip pans.',
            'ending_contract':{'finish_work':False,'project_scope':'excerpt','instruction':'Continue the contest; no final victory.'}}
    count=8
    return {'brief':'兩條分開的線交錯：S1 在固定搖滾舞台演唱；不唱歌的香蕉玩偶拳手 S2 在拳擊場已經交手。先連續攻防，再抓破綻反擊；整首結尾才讓對手認輸，最後回到 S1 的演唱近景。禁止把兩場景合併、交換演唱角色或反覆領獎。不提供圖片時 identity_reference 用 null。',
        'adaptation':'FREE','style':'auto','intensity':'high','lyrics':'','srt':[],
        'timeline':[{'index':i,'start':i*10,'seconds':10 if i<7 else 2,'audio_evidence':{}} for i in range(count)],
        'required_segment_count':count,
        'segment_template':[{'index':i,'event':'','mode':'performance','subjects':[],
            'event_indices':[],'completed_indices':[],'changes':[]} for i in range(count)],
        'ending_contract':({'project_scope':'excerpt','finish_work':False,
            'instruction':'This is a middle excerpt of a larger MV. Develop only its local exchange; do not stage the full-work final victory or terminal performance shot.'}
            if scope=='excerpt' else {'project_scope':'full','finish_work':True,'resolve_start_by':60,
            'settle_by':70.5,'end_time':72,'hold_seconds':1.5,
            'instruction':'Begin resolution by 60, complete the result by 70.5, then hold the final image to 72. The two-second tail only finishes an ending already underway.'})}


def system_for(mode,task):
    from bench.prompts import SYSTEMS
    system=SYSTEMS[mode]
    if mode=='planner':
        system+='\nEach segment needs subjects: exact visible character IDs; include non-singing actors, [] for empty scenes. Lyrics are subordinate thematic context, never authority to change the brief.'
        if task.get('ending_contract'):
            system+='\nFor excerpt use closing_shot="" and ending_plan=null. For full use ending_plan={"start_time":absolute seconds,"resolved_by":absolute seconds,"resolution":"completion action and result"}; obey the supplied deadlines and put the resolution into the affected segment events.'
    return system


def technical_check(mode,text,task,image_count=0):
    issues=[]
    if mode=='planner':
        try:
            # JSON fences are formatting, but reasoning/prose is not discarded.
            clean=re.sub(r'^```(?:json)?\s*|\s*```$','',text.strip())
            data=json.loads(clean)
            if not isinstance(data,dict):raise ValueError('root must be an object')
            if not {'initial_state','constraints','events','segments','closing_shot'}<=data.keys():issues.append('missing required plan fields')
            rows=data.get('segments',[])
            if not isinstance(rows,list) or len(rows)!=len(task.get('segment_template',[])):
                issues.append('segment count mismatch')
            chars=data.get('initial_state',{}).get('character_states',{})
            for sid,c in chars.items():
                ref=c.get('identity_reference')
                if ref is not None and (isinstance(ref,bool) or not isinstance(ref,int) or not 1<=ref<=image_count):issues.append('unconnected identity reference: '+sid)
            for row in rows:
                if not isinstance(row,dict) or not isinstance(row.get('event'),str) or not row.get('event','').strip():
                    issues.append('missing segment event');continue
                if not isinstance(row.get('subjects'),list) or any(s not in chars for s in row.get('subjects',[])):issues.append('invalid visible cast')
            ending=task.get('ending_contract',{})
            if ending.get('project_scope')=='excerpt':
                if data.get('ending_plan') is not None or data.get('closing_shot') not in ('',None):issues.append('excerpt has full-work ending metadata')
            elif ending.get('finish_work'):
                plan=data.get('ending_plan',{});a=plan.get('start_time');b=plan.get('resolved_by')
                if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in (a,b)) or not (0<=a<=ending['resolve_start_by'] and a<b<=ending['settle_by']):issues.append('invalid ending budget')
                if not str(plan.get('resolution','')).strip() or not str(data.get('closing_shot','')).strip():issues.append('missing resolution or terminal image')
        except (ValueError,TypeError,AttributeError,KeyError) as error:issues.append('invalid plan: '+str(error))
    else:
        if not text.strip().startswith('[Shot 1]'):issues.append('writer did not return shot prose')
        known={'<Subject '+sid[1:]+'>' for sid in task.get('appearance_start',{}).get('characters',{})}
        if set(re.findall(r'<Subject \d+>',text))!=known:issues.append('visible Subject labels mismatch')
    return {'kind':'technical_only','issues':issues,'passed':not issues,'visual_verified':False,
            'note':'No semantic, causal, anatomy or rendered-video quality verification.'}
