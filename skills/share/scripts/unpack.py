#!/usr/bin/env python3
"""Read a share-card-v1 HTML without executing it; verify or unpack its ZIP."""
import argparse
import base64
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import shutil
import stat
import unicodedata
import zipfile

MAX_BYTES = 512 * 1024 * 1024


def safe_path(value):
    if not isinstance(value, str) or not value or len(value) > 240:
        raise ValueError('Invalid file path')
    if '\\' in value or ':' in value or any(ord(c) < 32 for c in value):
        raise ValueError('Non-portable file path: ' + value)
    parts = value.split('/')
    for part in parts:
        if part in ('', '.', '..') or part.endswith(('.', ' ')):
            raise ValueError('Unsafe file path: ' + value)
        if re.search(r'[<>"|?*]', part) or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part, re.I):
            raise ValueError('Non-portable file path: ' + value)
    return value


def validate_paths(paths):
    keys = set()
    for path in paths:
        safe_path(path)
        key = unicodedata.normalize('NFC', path).casefold()
        if key in keys:
            raise ValueError('Duplicate/colliding file path: ' + path)
        keys.add(key)
    for key in keys:
        parts = key.split('/')
        if any('/'.join(parts[:i]) in keys for i in range(1, len(parts))):
            raise ValueError('File/directory path collision')


class Blocks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.blocks = {}
        self.active = None

    def handle_starttag(self, tag, attrs):
        identity = dict(attrs).get('id')
        if tag == 'script' and identity in ('share-manifest', 'share-payload'):
            if identity in self.blocks:
                raise ValueError('Duplicate data block')
            self.active = identity
            self.blocks[identity] = ''

    def handle_endtag(self, tag):
        if tag == 'script':
            self.active = None

    def handle_data(self, data):
        if self.active:
            self.blocks[self.active] += data


def read_card(card):
    parser = Blocks()
    parser.feed(Path(card).read_text(encoding='utf-8'))
    manifest = json.loads(parser.blocks['share-manifest'])
    if manifest.get('format') != 'share-card' or manifest.get('version') != 1:
        raise ValueError('Unsupported share card format/version')
    archive = base64.b64decode(''.join(parser.blocks['share-payload'].split()), validate=True)
    return manifest, archive


def verified_files(card):
    manifest, archive = read_card(card)
    if len(archive) != manifest['archive']['bytes'] or hashlib.sha256(archive).hexdigest() != manifest['archive']['sha256']:
        raise ValueError('Archive size/hash mismatch')
    entries = manifest['files']
    if not entries or any(type(f['bytes']) is not int or f['bytes'] < 0 for f in entries):
        raise ValueError('Invalid file inventory')
    if sum(f['bytes'] for f in entries) > MAX_BYTES:
        raise ValueError('Unpacked bundle exceeds 512 MiB limit')
    validate_paths([f['path'] for f in entries])
    expected = {f['path']: f for f in entries}
    result = []
    with zipfile.ZipFile(io.BytesIO(archive)) as package:
        members = package.infolist()
        validate_paths([f.filename for f in members])
        if set(f.filename for f in members) != set(expected):
            raise ValueError('Archive/manifest inventory mismatch')
        for member in members:
            entry = expected[member.filename]
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode) or member.is_dir() or member.file_size != entry['bytes']:
                raise ValueError('Invalid archive member: ' + member.filename)
            data = package.read(member)
            if hashlib.sha256(data).hexdigest() != entry['sha256']:
                raise ValueError('File hash mismatch: ' + member.filename)
            result.append((member.filename, data))
    return manifest, result


def extract(card, destination):
    manifest, files = verified_files(card)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    try:
        for name, data in files:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as output:
                output.write(data)
    except Exception:
        shutil.rmtree(destination)
        raise
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('card', type=Path)
    parser.add_argument('destination', nargs='?', type=Path, help='New directory; never an existing one')
    args = parser.parse_args()
    try:
        if args.destination:
            manifest = extract(args.card, args.destination)
        else:
            manifest, _ = verified_files(args.card)
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(1, 'share: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
