import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).with_name('share.py')


class ShareTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), 'Reusable card builder/extractor does not exist')
        spec = importlib.util.spec_from_file_location('share_card', SCRIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = bytes(range(256)) * 4
        (self.root / 'mesh.glb').write_bytes(self.data)
        (self.root / 'cover.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aMZkAAAAASUVORK5CYII='))
        self.config = self.root / 'spec.json'
        self.config.write_text(json.dumps({'title': 'Reed </script> Fox', 'creator': 'Test', 'rarity': 'rare', 'cover': 'cover.png', 'files': [{'source': 'mesh.glb', 'path': 'models/fox.glb'}]}))

    def build(self):
        output = self.root / 'card.html'
        self.mod.build(self.config, output)
        return output

    def rewrite(self, card, manifest, archive):
        text = card.read_text()
        old_manifest, old_archive = self.mod.read_card(card)
        manifest['archive']['bytes'] = len(archive)
        manifest['archive']['sha256'] = hashlib.sha256(archive).hexdigest()
        text = text.replace(self.mod.json_block(old_manifest), self.mod.json_block(manifest))
        text = text.replace(base64.b64encode(old_archive).decode(), base64.b64encode(archive).decode())
        card.write_text(text)

    def test_roundtrip_preserves_bytes_and_keeps_manifest_early(self):
        card = self.build()
        manifest, archive = self.mod.read_card(card)
        self.assertEqual(manifest['files'][0]['path'], 'models/fox.glb')
        self.assertNotIn(str(self.root), card.read_text())
        self.assertIn('share-manifest', card.read_text()[:3000])
        self.assertNotIn('Reed </script>', card.read_text())
        self.mod.extract(card, self.root / 'unpacked')
        self.assertEqual((self.root / 'unpacked/models/fox.glb').read_bytes(), self.data)

    def test_existing_destination_is_untouched(self):
        card = self.build()
        destination = self.root / 'existing'
        destination.mkdir()
        with self.assertRaises((ValueError, FileExistsError)):
            self.mod.extract(card, destination)
        self.assertEqual(list(destination.iterdir()), [])

    def test_corrupt_archive_is_rejected_before_writes(self):
        card = self.build()
        text = card.read_text()
        _, archive = self.mod.read_card(card)
        card.write_text(text.replace(base64.b64encode(archive).decode(), base64.b64encode(archive[:-1] + b'!').decode()))
        with self.assertRaises(ValueError):
            self.mod.extract(card, self.root / 'unpacked')
        self.assertFalse((self.root / 'unpacked').exists())

    def test_traversal_and_extra_files_are_rejected(self):
        for path in ('../escape', '/escape', 'C:/escape', 'a\\escape', 'extra.glb'):
            with self.subTest(path=path):
                card = self.root / 'card.html'
                if card.exists():
                    card.unlink()
                card = self.build()
                manifest, _ = self.mod.read_card(card)
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, 'w') as z:
                    z.writestr(path, b'bad')
                self.rewrite(card, manifest, buf.getvalue())
                with self.assertRaises(ValueError):
                    self.mod.extract(card, self.root / 'unpacked')
                self.assertFalse((self.root / 'unpacked').exists())

    def test_per_file_hash_is_checked(self):
        card = self.build()
        manifest, _ = self.mod.read_card(card)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('models/fox.glb', b'x' * len(self.data))
        self.rewrite(card, manifest, buf.getvalue())
        with self.assertRaises(ValueError):
            self.mod.extract(card, self.root / 'unpacked')
        self.assertFalse((self.root / 'unpacked').exists())

    def test_build_rejects_case_collisions_and_symlink_inputs(self):
        cfg = json.loads(self.config.read_text())
        cfg['files'].append({'source': 'mesh.glb', 'path': 'MODELS/Fox.glb'})
        self.config.write_text(json.dumps(cfg))
        with self.assertRaises(ValueError):
            self.build()

        cfg['files'] = [{'source': 'link.glb', 'path': 'fox.glb'}]
        (self.root / 'link.glb').symlink_to(self.root / 'mesh.glb')
        self.config.write_text(json.dumps(cfg))
        with self.assertRaises(ValueError):
            self.build()
    def test_level_is_an_integer_between_zero_and_ninety_nine(self):
        cfg = json.loads(self.config.read_text())
        for invalid in (-1, 100, True, '17', 17.5):
            with self.subTest(level=invalid):
                cfg['level'] = invalid
                self.config.write_text(json.dumps(cfg))
                (self.root / 'card.html').unlink(missing_ok=True)
                with self.assertRaises(ValueError):
                    self.build()
        for valid in (0, 99):
            cfg['level'] = valid
            self.config.write_text(json.dumps(cfg))
            card = self.root / 'card.html'
            if card.exists():
                card.unlink()
            self.build()
            self.assertEqual(self.mod.read_card(card)[0]['level'], valid)



if __name__ == '__main__':
    unittest.main()
