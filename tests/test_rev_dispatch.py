"""Exercise an independently installed Rev bundle without calling paid models."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def isolated_review(tmp_path):
    bundle = tmp_path / 'installed-rev'
    shutil.copytree(ROOT / 'skills/rev', bundle)
    work = bundle / 'review'
    assert (work / 'schema.json').is_file()
    assert (work / 'scripts/preflight.py').is_file()
    for mode in ('rev1', 'rev2', 'rev3', 'revx', 'revxflash', 'revxhigh', 'revxultra'):
        assert (bundle / 'references/shortcuts' / f'{mode}.md').is_file()
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    stub = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
Path(os.environ['CAPTURE']).write_text(json.dumps(args))
sys.stdin.read()
if os.environ.get('STUB_FAIL'):
    sys.exit(42)
reply = {'agent': 'code-quality', 'scope': ['fixture.py'], 'status': 'pass',
         'findings': [], 'summary': 'Reviewed fixture.py replacement; no defects found.'}
if os.environ.get('STUB_ECHO_SCHEMA'):
    reply = {'type': 'object', 'properties': {}}
if Path(sys.argv[0]).name == 'codex':
    Path(args[args.index('-o') + 1]).write_text(json.dumps(reply))
else:
    print(json.dumps({'result': json.dumps(reply), 'usage': {}}))
'''
    for name in ('codex', 'claude'):
        p = fake_bin / name
        p.write_text(stub)
        p.chmod(0o755)
    home = tmp_path / 'home'
    home.mkdir()
    prompt = tmp_path / 'prompt.md'
    prompt.write_text('Review fixture.py and return findings.')
    diff = tmp_path / 'diff.patch'
    diff.write_text('diff --git a/fixture.py b/fixture.py\n--- a/fixture.py\n+++ b/fixture.py\n@@ -1 +1 @@\n-old\n+new\n')
    capture = tmp_path / 'argv.json'
    env = {**os.environ, 'HOME': str(home), 'PATH': f'{fake_bin}:{os.environ["PATH"]}',
           'CAPTURE': str(capture)}
    return work, prompt, diff, capture, env, tmp_path


def dispatch(fixture, backend='codex', extra=(), env_extra=None):
    work, prompt, diff, capture, env, tmp = fixture
    output = tmp / 'result.json'
    command = ['bash', str(work / 'dispatch.sh'), f'--tool={backend}', '--timeout=0',
               *extra, 'code-quality', str(prompt), str(diff), str(output)]
    result = subprocess.run(command, env={**env, **(env_extra or {})},
                            capture_output=True, text=True, timeout=15)
    return result, output, json.loads(capture.read_text())


@pytest.mark.parametrize('backend,extra,model,effort', [
    ('codex', (), 'gpt-6.1-sol', 'high'),
    ('claude', (), 'sonnet', 'high'),
    ('claude', ('--effort=xhigh',), 'sonnet', 'xhigh'),
])
def test_model_and_effort_routing(isolated_review, backend, extra, model, effort):
    result, output, args = dispatch(isolated_review, backend, extra)
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text())['status'] == 'pass'
    model_flag = '-m' if backend == 'codex' else '--model'
    assert args[args.index(model_flag) + 1] == model
    if backend == 'claude':
        assert args[args.index('--effort') + 1] == effort
    else:
        assert f'model_reasoning_effort={effort}' in args


def test_backend_failure_is_not_reported_as_success(isolated_review):
    result, output, _ = dispatch(isolated_review, env_extra={'STUB_FAIL': '1'})
    assert result.returncode != 0
    assert not output.exists()


def test_schema_echo_is_rejected(isolated_review):
    result, output, _ = dispatch(isolated_review, env_extra={'STUB_ECHO_SCHEMA': '1'})
    assert result.returncode != 0
    assert not output.exists()
    assert Path(str(output) + '.rejected').exists()
