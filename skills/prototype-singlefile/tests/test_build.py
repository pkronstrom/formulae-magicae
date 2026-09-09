import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BuildTests(unittest.TestCase):
    def test_portable_build_and_revision(self):
        script = ROOT / 'scripts/build.py'
        self.assertTrue(script.exists(), 'Missing reusable builder')
        spec = importlib.util.spec_from_file_location('build', script)
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / 'screen.html').write_text('<h1>Original</h1>')
            manifest = {'title': 'Review', 'frames': [{'id': 'home', 'title': 'Home', 'file': 'screen.html'}]}
            (path / 'screens.json').write_text(json.dumps(manifest))
            build.build(path / 'screens.json', path / 'canvas.html')
            first = build.read_state(path / 'canvas.html')
            first['comments'] = [{'id': 'c1', 'frameId': 'home', 'x': 10, 'y': 20, 'text': '</script><script>bad()</script>', 'resolved': False}]
            first['frames'][0]['x'] = 789
            build.write_html(path / 'canvas.html', first)
            self.assertEqual(build.read_state(path / 'canvas.html')['comments'], first['comments'])
            self.assertNotIn('</script><script>bad()', (path / 'canvas.html').read_text())
            (path / 'screen.html').write_text('<h1>Revised</h1>')
            build.build(path / 'screens.json', path / 'canvas.html')
            revised = build.read_state(path / 'canvas.html')
            self.assertEqual(revised['frames'][0]['x'], 789)
            self.assertEqual(revised['comments'], first['comments'])
            self.assertIn('Revised', revised['frames'][0]['html'])
            self.assertEqual(revised['id'], first['id'])
            self.assertGreater(revised['revision'], first['revision'])

    def test_invalid_manifest_does_not_replace_artifact(self):
        script = ROOT / 'scripts/build.py'
        self.assertTrue(script.exists(), 'Missing reusable builder')
        spec = importlib.util.spec_from_file_location('build', script)
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / 'canvas.html').write_text('keep me')
            (path / 'screens.json').write_text('{"frames": []}')
            with self.assertRaises(ValueError):
                build.build(path / 'screens.json', path / 'canvas.html')
            self.assertEqual((path / 'canvas.html').read_text(), 'keep me')


if __name__ == '__main__':
    unittest.main()
