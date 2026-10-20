#!/usr/bin/env python3
"""Build an offline collectible asset card from an explicit JSON specification."""
import argparse
import base64
import hashlib
import html
import io
import json
from pathlib import Path
import runpy
import zipfile

HERE = Path(__file__).resolve().parent
_unpack = runpy.run_path(str(HERE / 'unpack.py'))
read_card = _unpack['read_card']
extract = _unpack['extract']
validate_paths = _unpack['validate_paths']


def json_block(value):
    return json.dumps(value, indent=2, ensure_ascii=False).replace('<', '\\u003c').replace('&', '\\u0026')


def source_path(base, value):
    path = base / value
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError('Symlink inputs are not supported: ' + str(path))
    if not path.is_file():
        raise ValueError('Expected an explicit regular file: ' + str(path))
    return path


def build(spec, output):
    spec, output = Path(spec).resolve(), Path(output)
    cfg = json.loads(spec.read_text(encoding='utf-8'))
    level = cfg.get('level', 1)
    if type(level) is not int or not 0 <= level <= 99:
        raise ValueError('Level must be an integer from 0 to 99')
    rarity = cfg.get('rarity', 'rare')
    if rarity not in ('common', 'uncommon', 'rare', 'legendary'):
        raise ValueError('Rarity must be common, uncommon, rare or legendary')
    files = cfg['files']
    if not files:
        raise ValueError('Include at least one file')
    validate_paths([entry['path'] for entry in files])
    cover = source_path(spec.parent, cfg['cover'])
    mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}.get(cover.suffix.lower())
    if mime is None:
        raise ValueError('Cover must be a PNG, JPEG or WebP screenshot')
    archive_buffer = io.BytesIO()
    inventory = []
    total = 0
    with zipfile.ZipFile(archive_buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for entry in files:
            source = source_path(spec.parent, entry['source'])
            data = source.read_bytes()
            total += len(data)
            if total > _unpack['MAX_BYTES']:
                raise ValueError('Unpacked bundle exceeds 512 MiB limit')
            archive.writestr(entry['path'], data)
            inventory.append({'path': entry['path'], 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'role': entry.get('role', 'asset')})
    archive_bytes = archive_buffer.getvalue()
    manifest = {
        'format': 'share-card', 'version': 1,
        'title': cfg['title'], 'creator': cfg.get('creator', 'Unknown creator'),
        'edition': cfg.get('edition', '01'), 'rarity': rarity,
        'foil': True, 'type': cfg.get('type', 'Polygonster'), 'level': level,
        'tagline': cfg.get('tagline', ''), 'vitals': cfg.get('vitals', ''),
        'skill': cfg.get('skill', {'name': 'Suspiciously Useful', 'description': 'Does one thing very well. Refuses to elaborate.'}),
        'description': cfg.get('description', ''), 'lore': cfg.get('lore', ''),
        'provenance': cfg.get('provenance', ''), 'license': cfg.get('license', 'Not specified'),
        'stats': cfg.get('stats', {}), 'files': inventory,
        'archive': {'encoding': 'base64', 'type': 'application/zip', 'bytes': len(archive_bytes), 'sha256': hashlib.sha256(archive_bytes).hexdigest()},
    }
    template = (HERE.parent / 'assets' / 'card.html').read_text(encoding='utf-8')
    background = ''
    if cfg.get('background'):
        backdrop = source_path(spec.parent, cfg['background'])
        bg_mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}.get(backdrop.suffix.lower())
        if not bg_mime:
            raise ValueError('Background must be a PNG, JPEG or WebP')
        background = 'data:' + bg_mime + ';base64,' + base64.b64encode(backdrop.read_bytes()).decode()
    replacements = {
        'BACKGROUND': background,
        'MANIFEST': json_block(manifest),
        'TITLE': html.escape(cfg['title']),
        'COVER': 'data:' + mime + ';base64,' + base64.b64encode(cover.read_bytes()).decode(),
        'PAYLOAD': base64.b64encode(archive_bytes).decode(),
        'EXTRACTOR': html.escape((HERE / 'unpack.py').read_text(encoding='utf-8')),
    }
    # One pass prevents placeholder-like author text from being substituted twice.
    import re
    result = re.sub(r'@@(MANIFEST|TITLE|COVER|PAYLOAD|EXTRACTOR|BACKGROUND)@@', lambda match: replacements[match[1]], template)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as file:
        file.write(result)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', type=Path, help='JSON spec; source and cover paths relative to this file')
    parser.add_argument('output', type=Path, help='New .html file; refuses to overwrite')
    args = parser.parse_args()
    try:
        manifest = build(args.spec, args.output)
        print(json.dumps({'output': str(args.output.resolve()), 'html_bytes': args.output.stat().st_size, 'asset_bytes': sum(f['bytes'] for f in manifest['files']), 'files': len(manifest['files'])}, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(1, 'share: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
