#!/usr/bin/env python3
"""Assemble portable screen canvases, preserving saved review state on revision."""
import argparse
import json
from pathlib import Path
import re
import time
import uuid

TEMPLATE = Path(__file__).resolve().parents[1] / 'assets/template.html'
BLOCK = re.compile(r'(<script id="prototype-data" type="application/json">)\s*(.*?)\s*(</script>)', re.S)


def read_state(path):
    match = BLOCK.search(Path(path).read_text())
    if not match:
        raise ValueError(f'No prototype-data block in {path}')
    data = json.loads(match[2])
    if data.get('v') != 1:
        raise ValueError('Unsupported document version')
    return data


def write_html(path, data):
    payload = json.dumps(data, indent=2, ensure_ascii=False).replace('<', '\\u003c')
    template = TEMPLATE.read_text()
    result, count = BLOCK.subn(lambda m: m[1] + '\n' + payload + '\n' + m[3], template)
    if count != 1:
        raise ValueError('Template must have exactly one data block')
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    temp = Path(str(path) + '.tmp')
    temp.write_text(result)
    temp.replace(path)


def build(manifest_path, output, prior=None):
    manifest_path, output = Path(manifest_path), Path(output)
    manifest = json.loads(manifest_path.read_text())
    frames = manifest.get('frames')
    if not isinstance(frames, list) or not frames:
        raise ValueError('Manifest needs at least one frame')
    ids = [f.get('id') for f in frames]
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('Frame IDs must be unique nonempty strings')
    old = read_state(prior or output) if prior or output.exists() else None
    now = int(time.time() * 1000)
    data = old or {'v': 1, 'id': str(uuid.uuid4()), 'revision': 0, 'savedAt': 0,
                   'viewport': {'x': 60, 'y': 70, 'z': .65}, 'frames': [], 'comments': [], 'strokes': []}
    previous = {f['id']: f for f in data['frames']}
    updated = []
    for i, frame in enumerate(frames):
        item = dict(previous.get(frame['id'], {}))
        item.update({'id': frame['id'], 'title': frame.get('title', frame['id']),
                     'html': (manifest_path.parent / frame['file']).read_text()})
        for key, default in [('x', (i % 3) * 460), ('y', (i // 3) * 860), ('w', 390), ('h', 760)]:
            item[key] = frame.get(key, item.get(key, default))
            if not isinstance(item[key], (int, float)) or not (-100000 <= item[key] <= 100000):
                raise ValueError(f'Invalid frame {key}')
        if item['w'] < 100 or item['h'] < 100:
            raise ValueError('Frame dimensions must be at least 100px')
        updated.append(item)
    data.update(title=manifest.get('title', data.get('title', 'Prototype canvas')), frames=updated,
                revision=data['revision'] + 1, savedAt=max(now, data['savedAt'] + 1))
    write_html(output, data)
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path, help='JSON with title and frames: id, title, file, optional x/y/w/h')
    parser.add_argument('output', type=Path, help='Self-contained output HTML; existing review state is preserved')
    parser.add_argument('--from-saved', type=Path, help='Use the user-saved HTML as prior state')
    args = parser.parse_args()
    try:
        state = build(args.manifest, args.output, args.from_saved)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f'error: {exc}\n')
    print(f'{args.output}: {len(state["frames"])} frames, revision {state["revision"]}')
