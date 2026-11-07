"""Extract a pinned upstream prompt without importing/executing its Comfy code."""
import ast
import hashlib
from pathlib import Path

T8_COMMIT = '25a8caafac8d4d77f5d0e11b6c01f1491903d5f5'
T8_BLOB = '4f4bd39499d05649f9befe57b5de1bfeda50913f'
T8_URL = ('https://raw.githubusercontent.com/T8mars/'
          'comfyui-minimax-h3-prompt-enhancer-T8/' + T8_COMMIT + '/storyboard_director.py')
DEFAULT_PATH = Path(__file__).resolve().parents[1] / 'cache/t8/storyboard_director.py'


def _string(node, names):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in names:
        return names[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _string(node.left, names) + _string(node.right, names)
    raise ValueError('T8 固定來源的字串結構不符；不執行上游 Python。')


def load_method(path=DEFAULT_PATH):
    path = Path(path)
    if not path.is_file():
        raise ValueError('尚未準備 T8 固定來源；先執行 python tools/fetch_t8.py。')
    data = path.read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if blob != T8_BLOB:
        raise ValueError('T8 來源雜湊不符；停止測試，避免混用版本。')
    tree = ast.parse(data.decode('utf-8'))
    names = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = getattr(node.targets[0], 'id', '')
            if name in ('REVISION', 'MARKER'):
                names[name] = _string(node.value, names)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'storyboard_instruction')
    shot_if = next(n for n in function.body if isinstance(n, ast.If)
                   and 'fixed_shot_count' in ast.unparse(n.test))
    shot_assign = shot_if.orelse[0].orelse[0]  # fixed_shot_count=0 (AUTO)
    names['shot_rule'] = _string(shot_assign.value, names)
    native = next(n for n in function.body if isinstance(n, ast.Assign)
                  and getattr(n.targets[0], 'id', '') == 'native')
    names['native'] = _string(native.value.body, names)  # model_target='h3'
    returned = next(n.value for n in function.body if isinstance(n, ast.Return))
    # Only strings in the pinned final join tuple; no eval, exec or imports.
    method = '\n'.join(_string(n, names) for n in returned.args[0].elts)
    return method, {'repository': 'T8mars/comfyui-minimax-h3-prompt-enhancer-T8',
                    'commit': T8_COMMIT, 'git_blob_sha1': blob,
                    'file_sha256': hashlib.sha256(data).hexdigest(),
                    'method_sha256': hashlib.sha256(method.encode()).hexdigest(),
                    'revision': names['REVISION'], 'target': 'h3', 'shot_choice': 'AUTO',
                    'scope': 'storyboard modifier only; not the complete T8 enhancer'}
