import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('writer', ROOT / 'write-snapshot.py')
writer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(writer)

SNAPSHOT = json.dumps({'deviceId': 'laptop', 'providers': {}})


class WriteSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def test_writes_owner_only_file_atomically(self):
        writer.publish(self.path, 'laptop.json', SNAPSHOT)
        target = self.path / 'laptop.json'
        self.assertEqual(json.loads(target.read_text())['deviceId'], 'laptop')
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual([p.name for p in self.path.iterdir()], ['laptop.json'])

    def test_planted_symlink_is_replaced_not_followed(self):
        victim = self.path / 'victim'
        victim.write_text('ORIGINAL')
        (self.path / 'laptop.json').symlink_to(victim)
        writer.publish(self.path, 'laptop.json', SNAPSHOT)
        self.assertEqual(victim.read_text(), 'ORIGINAL')
        self.assertFalse((self.path / 'laptop.json').is_symlink())

    def test_planted_fifo_is_replaced_without_blocking(self):
        os.mkfifo(self.path / 'laptop.json')
        writer.publish(self.path, 'laptop.json', SNAPSHOT)
        self.assertTrue((self.path / 'laptop.json').is_file())

    def test_rejects_bad_names_size_and_content(self):
        for name in ('../x.json', '.hidden.json', 'a/b.json', 'x.txt', ''):
            with self.assertRaises(ValueError):
                writer.publish(self.path, name, SNAPSHOT)
        with self.assertRaises(ValueError):
            writer.publish(self.path, 'a.json', ' ' * (writer.MAX_SNAPSHOT_BYTES + 1))
        for text in ('[]', '{', ''):
            with self.assertRaises(ValueError):
                writer.publish(self.path, 'a.json', text)
        self.assertEqual(list(self.path.iterdir()), [])

    def test_cli_reads_snapshot_from_environment(self):
        env = dict(os.environ, OMAGOBLIN_SNAPSHOT=SNAPSHOT)
        subprocess.run(['python3', ROOT / 'write-snapshot.py', self.path, 'laptop.json'], env=env, check=True, timeout=10)
        self.assertTrue((self.path / 'laptop.json').is_file())
        env.pop('OMAGOBLIN_SNAPSHOT')
        result = subprocess.run(['python3', ROOT / 'write-snapshot.py', self.path, 'b.json'], env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, 'Usage sync write failed\n')


if __name__ == '__main__':
    unittest.main()
