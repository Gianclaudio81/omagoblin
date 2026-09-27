import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('refresh', Path(__file__).resolve().parents[1] / 'refresh-claude.py')
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)


class ClaudeRefreshTest(unittest.TestCase):
    def test_rate_limit_keeps_data_marks_stale_and_cools_down(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = {}
            probe = Mock(return_value={'ok': False, 'helpText': 'endpoint is rate limiting checks'})
            scope = {'probe_limits': probe}
            exec('def collect(token, expiry, force):\n r = probe_limits(token)\n return {"limits": [{"percent": 0.2}], "usageStatusText": ""}\n', scope)
            module = {'collect_limits': scope['collect'], 'cache_root': lambda: Path(tmp),
                      'read_fresh_json': lambda *a: state,
                      'write_json': lambda path, value: state.update(value)}
            result = refresh.guarded_collect(module, 'test', 0, False)
            self.assertEqual(result['limits'][0]['percent'], 0.2)
            self.assertEqual(result['usageStatusText'], 'Claude limits outdated')
            self.assertEqual(state['delay'], 300)
            refresh.guarded_collect(module, 'test', 0, True)
            self.assertEqual(probe.call_count, 1)
            self.assertIs(scope['probe_limits'], probe)
