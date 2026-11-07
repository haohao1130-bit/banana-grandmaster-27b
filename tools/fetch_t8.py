"""Explicitly download one pinned T8 file into ignored local cache; never execute it."""
from pathlib import Path
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench.t8_adapter import DEFAULT_PATH, T8_URL, load_method


def prepare():
    DEFAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # A valid offline cache is sufficient; a mismatched one must be inspected.
    if not DEFAULT_PATH.exists():
        data = urllib.request.urlopen(T8_URL, timeout=30).read(128 * 1024)
        candidate = DEFAULT_PATH.with_suffix('.download')
        candidate.write_bytes(data)
        try:
            load_method(candidate)
            candidate.replace(DEFAULT_PATH)
        finally:
            candidate.unlink(missing_ok=True)
    _, metadata = load_method(DEFAULT_PATH)
    print('T8 source verified:', metadata['commit'], metadata['git_blob_sha1'])


if __name__ == '__main__':
    prepare()
