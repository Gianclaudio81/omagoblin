import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('usage', ROOT / 'read-usage.py')
usage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usage)


def record(agent_id='codex'):
    return {'id': agent_id, 'ready': True, 'limits': [{'percent': 0.4}]}


class ReadUsageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def write(self, name, value):
        (self.path / name).write_text(json.dumps(value))

    def test_valid_records_sorted(self):
        self.write('codex.json', record('codex'))
        self.write('claude.json', record('claude'))
        result = usage.scan(self.path)
        self.assertEqual([item['agentId'] for item in result['records']], ['claude', 'codex'])
        self.assertEqual(result['records'][1]['record'], record('codex'))
        self.assertEqual(result['rejected'], 0)

    def test_fifo_symlink_directory_and_oversize_rejected_without_blocking(self):
        self.write('target', record())
        (self.path / 'link.json').symlink_to(self.path / 'target')
        (self.path / 'directory.json').mkdir()
        os.mkfifo(self.path / 'pipe.json')
        (self.path / 'huge.json').write_bytes(b' ' * (usage.MAX_FILE_BYTES + 1))
        result = usage.scan(self.path)
        self.assertEqual(result['records'], [])
        self.assertEqual(result['rejected'], 4)

    def test_file_swapped_for_fifo_after_stat_does_not_block(self):
        self.write('codex.json', record())
        real_open = os.open

        def swap(name, flags, *args, **kwargs):
            if name == 'codex.json':
                os.unlink(self.path / name)
                os.mkfifo(self.path / name)
            return real_open(name, flags, *args, **kwargs)

        with patch.object(usage.os, 'open', side_effect=swap):
            result = usage.scan(self.path)
        self.assertEqual(result['records'], [])
        self.assertEqual(result['rejected'], 1)

    def test_foreign_owner_rejected(self):
        self.write('codex.json', record())
        with patch.object(usage.os, 'getuid', return_value=os.getuid() + 1):
            with self.assertRaises(ValueError):
                usage.scan(self.path)

    def test_bad_names_and_content_rejected(self):
        self.write('../x.json'.replace('../', 'bad name'), record())
        (self.path / 'broken.json').write_text('{')
        (self.path / 'list.json').write_text('[]')
        (self.path / 'dupe.json').write_text('{"a":1,"a":2}')
        (self.path / 'proto.json').write_text('{"__proto__":{}}')
        result = usage.scan(self.path)
        self.assertEqual(result['records'], [])
        self.assertEqual(result['rejected'], 5)

    def test_missing_directory_is_empty(self):
        result = usage.scan(self.path / 'missing')
        self.assertEqual(result, {'records': [], 'rejected': 0, 'limited': False})

    def test_file_budget_is_limited(self):
        for index in range(usage.MAX_FILES + 1):
            self.write(f'a{index:03}.json', record())
        result = usage.scan(self.path)
        self.assertEqual(len(result['records']), usage.MAX_FILES)
        self.assertTrue(result['limited'])

    def test_cli_emits_envelope(self):
        self.write('codex.json', record())
        output = subprocess.run(['python3', ROOT / 'read-usage.py', self.path], capture_output=True, text=True, check=True, timeout=10)
        self.assertEqual(json.loads(output.stdout)['records'][0]['agentId'], 'codex')


if __name__ == '__main__':
    unittest.main()
