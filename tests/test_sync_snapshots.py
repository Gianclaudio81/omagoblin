import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reader', ROOT / 'sync-snapshots.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def snapshot():
    return {'deviceId': 'laptop', 'providers': {'codex': {'todayPrompts': 3}}}


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def write(self, name, value):
        (self.path / name).write_text(json.dumps(value, ensure_ascii=False))

    def test_valid_and_invalid(self):
        self.write('valid.json', snapshot())
        (self.path / 'broken.json').write_text('{')
        result = reader.scan(self.path)
        self.assertEqual(result['snapshots'], [snapshot()])
        self.assertEqual(result['rejected'], 1)

    def test_nonregular_and_oversize(self):
        self.write('target', snapshot())
        (self.path / 'link.json').symlink_to(self.path / 'target')
        (self.path / 'directory.json').mkdir()
        os.mkfifo(self.path / 'pipe.json')
        with (self.path / 'large.json').open('wb') as stream:
            stream.truncate(reader.MAX_FILE_BYTES + 1)
        result = reader.scan(self.path)
        self.assertEqual(result['snapshots'], [])
        self.assertEqual(result['rejected'], 4)

    def test_swap_before_open(self):
        for kind in ('symlink', 'fifo'):
            with self.subTest(kind=kind):
                self.write('race.json', snapshot())
                original = os.open
                def racing_open(name, flags, **kwargs):
                    if name == 'race.json':
                        (self.path / name).unlink()
                        if kind == 'symlink':
                            (self.path / name).symlink_to('/dev/zero')
                        else:
                            os.mkfifo(self.path / name)
                    return original(name, flags, **kwargs)
                with patch.object(reader.os, 'open', side_effect=racing_open):
                    result = reader.scan(self.path)
                self.assertEqual(result['rejected'], 1)
                (self.path / 'race.json').unlink()

    def test_candidate_count(self):
        for i in range(reader.MAX_FILES + 5):
            self.write(f'{i}.json', snapshot())
        result = reader.scan(self.path)
        self.assertEqual(len(result['snapshots']), reader.MAX_FILES)
        self.assertTrue(result['limited'])

    def test_entry_count(self):
        for i in range(reader.MAX_ENTRIES + 1):
            (self.path / str(i)).touch()
        self.assertTrue(reader.scan(self.path)['limited'])

    def test_malformed_cardinality_and_depth(self):
        cases = [
            {'providers': []},
            {'providers': {'codex': []}},
            {'providers': {}, 'extra': [0] * (reader.MAX_CONTAINER + 1)},
            {'providers': {}, 'extra': [[0] * 3000] * 3},
            {'providers': {str(i): {} for i in range(33)}},
            {'providers': {'__proto__': {}}},
            {'providers': {}, 'extra': float('inf')},
        ]
        deep = 0
        for _ in range(20):
            deep = [deep]
        cases.append({'providers': {}, 'extra': deep})
        for i, value in enumerate(cases):
            self.write(f'{i}.json', value)
        (self.path / 'duplicates.json').write_text('{"providers":{},"providers":{}}')
        result = reader.scan(self.path)
        self.assertEqual(result['snapshots'], [])
        self.assertEqual(result['rejected'], len(cases) + 1)

    def test_total_read_budget(self):
        raw = json.dumps(snapshot()).encode().ljust(reader.MAX_FILE_BYTES, b' ')
        for i in range(12):
            (self.path / f'{i}.json').write_bytes(raw)
        result = reader.scan(self.path)
        self.assertEqual(len(result['snapshots']), 8)
        self.assertTrue(result['limited'])

    def test_total_nodes(self):
        value = {'providers': {}, 'extra': [0] * 4000}
        for i in range(12):
            self.write(f'{i}.json', value)
        result = reader.scan(self.path)
        self.assertLessEqual(sum(reader.validate(v) for v in result['snapshots']), reader.MAX_TOTAL_NODES)
        self.assertTrue(result['limited'])

    def test_output_expansion_budget(self):
        value = {'providers': {}, 'extra': ['é' * 250] * 300}
        for i in range(16):
            self.write(f'{i}.json', value)
        result = subprocess.run(['python3', str(ROOT / 'sync-snapshots.py'), str(self.path)], capture_output=True, timeout=7, check=True)
        self.assertLessEqual(len(result.stdout), reader.MAX_OUTPUT_BYTES)
        self.assertTrue(json.loads(result.stdout)['limited'])
        self.assertEqual(result.stderr, b'')

    def test_cli_failure_is_bounded(self):
        result = subprocess.run(['python3', str(ROOT / 'sync-snapshots.py'), str(self.path / 'missing')], capture_output=True, timeout=7)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b'')
        self.assertEqual(result.stderr, b'Usage sync scan failed\n')


if __name__ == '__main__':
    unittest.main()
