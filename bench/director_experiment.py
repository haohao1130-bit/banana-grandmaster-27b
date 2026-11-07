"""Same-model, same-input storyboard Off/On experiment; no H3 rendering."""
import copy
import hashlib
import json
import math
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from bench.runner import HFBackend, MODELS, atomic_json
from bench.t8_adapter import load_method


DIRECTOR_SYSTEM = """You are the creative director and editor of this music-video passage.
The user supplies the story spine and hard constraints; independently invent the
performance, staging, visual coverage, camera choices and editing that make it compelling.
Preserve assigned identities, separate locations, causal milestones and required result.
Reference images define identity and specified appearance; expressions, gaze and poses
are performances you direct, except explicit performance locks or boundary frames.
Use supplied cue labels for vocalist identity and timing. Lyrics inform meaning, not
literal shot-by-shot illustration. You do not hear audio: acoustic measurements cannot
identify vocal emotion. H3 receives the source audio unchanged; only permitted singers
lip-sync. Do not author dialogue, quote lyrics, add subtitles or add sounds to the song.
Choose the sequence of visible information and its emotional progression, then write
concrete shots with framing, light, action, camera movement and continuity. Select
shot sizes and lengths by their purpose; commit to your choices without a fixed quota.
Return only an English Ref2VA draft with these six plain-text headers in order:
subject_definitions, summary, retention_analysis, detailed_description,
overall_soundscape, non_diegetic_music (each followed by a colon).
Use actual <Picture N> bindings and stable <Subject N> labels. Preserve identity in
retention_analysis; put changing performance in the shots. In detailed_description,
start [Shot 1] at zero without a timestamp; each later [Shot N] starts at its local
MM:SS.mmm cut time inside the requested duration. Continue actions across cuts.
State <Audio 1>: fully_copy for the source soundtrack; non_diegetic_music is N/A.
"""


def director_preset():
    return {
        'seconds': 15,
        'adaptation': 'FREE',
        'brief': 'A furious musician discovers an automated revision has ruined his work. '
                 'Intercut his cramped night studio with a cheerful service agent in a '
                 'separate bright white control room. Her confident operation causes a '
                 'visible new mistake; he notices the result and reacts. Invent the '
                 'acting, physical details, photography and montage. The absurd contrast '
                 'should build, while the larger dispute stays unresolved.',
        'reference_roles': {},
        'source_audio': 'Supplied to H3 only; neither model hears it in this test.',
        'performance_context': 'User-directed contrast: physical, explosive frustration '
                               'versus composed, sweet confidence. This is a creative '
                               'instruction, not an analysis of the recording.',
        'local_vocal_cues': [
            {'start': 0, 'end': 5, 'vocalist': 'male musician'},
            {'start': 5, 'end': 8, 'vocalist': 'female service agent'},
            {'start': 8, 'end': 15, 'vocalist': 'male musician'}],
        'hard_constraints': [
            'Locations remain separate; use full-frame intercuts.',
            'Only the cue-assigned character may lip-sync; the other may react silently.',
            'Preserve the source song; add no speech or sound layers.',
            'This passage is not the ending of the work.'],
    }


def compare_directors(task, images, settings, output_dir, method_path, backend=None,
                      progress=None):
    """Two calls to one model; raw outputs/errors are durable after each arm."""
    if not isinstance(task, dict):
        raise ValueError('任務必須是 JSON 物件。')
    seconds = float(task.get('seconds', 0))
    if isinstance(task.get('seconds'), bool) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('請指定正數秒數。')
    if not isinstance(task.get('brief'), str) or not task['brief'].strip():
        raise ValueError('請填入故事主軸。')
    cues = task.get('local_vocal_cues', [])
    if not isinstance(cues, list):
        raise ValueError('聲部時間需為 JSON 陣列。')
    for cue in cues:
        if not isinstance(cue, dict):
            raise ValueError('每個聲部時間需為 JSON 物件。')
        a, b = cue.get('start'), cue.get('end')
        if (not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(v) for v in (a, b)) or
                not 0 <= a < b <= seconds or
                not isinstance(cue.get('vocalist'), str) or not cue['vocalist'].strip()):
            raise ValueError('聲部時間需落在本段秒數內，並指定演唱角色。')
    if len(images) > 4:
        raise ValueError('本測試台最多四張參考圖。')
    model_label = settings.get('model_label', '27B')
    if model_label not in MODELS:
        raise ValueError('未知模型。')
    if settings.get('order', 'Off first') not in ('Off first', 'On first'):
        raise ValueError('未知對照順序。')
    seed, tokens = int(settings['seed']), int(settings['max_new_tokens'])
    if not 0 <= seed < 2**32 or not 1 <= tokens <= 8192:
        raise ValueError('Seed 或輸出上限不合法。')
    method, source = load_method(method_path)
    systems = {'off': DIRECTOR_SYSTEM, 'on': DIRECTOR_SYSTEM + '\n' + method}
    order = ['off', 'on'] if settings.get('order', 'Off first') == 'Off first' else ['on', 'off']
    sampling = dict(settings, seed=seed, max_new_tokens=tokens, temperature=.7,
                    top_p=.8, top_k=20, thinking=False, repetition_penalty=1.0)
    payload = json.dumps(task, ensure_ascii=False)
    run_id = time.strftime('%Y%m%d-%H%M%S') + '-director-' + uuid.uuid4().hex[:8]
    path = Path(output_dir) / (run_id + '.json')
    report = {
        'id': run_id, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'experiment': 'same_model_t8_storyboard_off_on_v1',
        'task': copy.deepcopy(task), 'payload': payload, 'systems': systems,
        'system_sha256': {k: hashlib.sha256(v.encode()).hexdigest() for k, v in systems.items()},
        'settings': sampling, 'order': order, 't8_source': source,
        'image_sha256': [hashlib.sha256(p.tobytes()).hexdigest() for p in images],
        'image_sizes': [list(p.size) for p in images],
        'image_modes': [p.mode for p in images],
        'arms': {}, 'visual_verified': False,
        'scope': 'Generic Qwen text experiment, not specialized H3 9B, '
                 'not the complete T8 enhancer, not Seedance or H3 video acceptance.',
    }
    atomic_json(path, report)
    backend = backend or HFBackend()
    # Freeze the model revision once for both arms. A lookup failure is recorded,
    # rather than silently switching weights or losing the prepared inputs.
    try:
        if isinstance(backend, HFBackend):
            from huggingface_hub import HfApi
            sampling['model_revision'] = HfApi().model_info(MODELS[model_label]).sha
            atomic_json(path, report)
        for arm in order:
            if progress:
                progress(model_label + ' · T8 ' + arm)
            try:
                result = backend.run(model_label, systems[arm], payload,
                                     images, copy.deepcopy(sampling))
            except Exception as error:
                result = {'status': 'error', 'model': MODELS[model_label],
                          'error_type': type(error).__name__, 'error': str(error)}
            report['arms'][arm] = result
            atomic_json(path, report)
    except Exception as error:
        report['setup_error'] = {'type': type(error).__name__, 'message': str(error)}
        atomic_json(path, report)
    return report, path
