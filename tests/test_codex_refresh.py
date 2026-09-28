import importlib.util
import io
import os
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('refresh_codex', Path(__file__).resolve().parents[1] / 'refresh-codex.py')
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)


class FakeProc:
    def __init__(self):
        read_fd, self.write_fd = os.pipe()
        self.stdout = os.fdopen(read_fd, 'r')
        self.stdin = io.StringIO()

    def send(self, text):
        os.write(self.write_fd, text.encode())

    def close(self):
        os.close(self.write_fd)
        self.stdout.close()


class CodexRefreshTest(unittest.TestCase):
    def setUp(self):
        self.proc = FakeProc()
        self.addCleanup(self.proc.close)

    def test_reply_sharing_a_chunk_with_notifications_is_not_lost(self):
        self.proc.send('{"id":1,"result":{}}\n{"method":"account/updated"}\n{"id":2,"result":{"account":{}}}\n')
        self.assertEqual(refresh.buffered_rpc_request(self.proc, 1, 'initialize', timeout=1)['id'], 1)
        # The second reply is already buffered: no further pipe data arrives.
        self.assertEqual(refresh.buffered_rpc_request(self.proc, 2, 'account/read', timeout=1)['id'], 2)

    def test_split_lines_and_garbage_are_handled(self):
        self.proc.send('not json\n{"id":3,')
        self.proc.send('"result":{}}\n')
        self.assertEqual(refresh.buffered_rpc_request(self.proc, 3, 'x', timeout=1)['id'], 3)

    def test_timeout_and_eof(self):
        with self.assertRaises(TimeoutError):
            refresh.buffered_rpc_request(self.proc, 9, 'x', timeout=0.3)
        os.close(self.proc.write_fd)
        self.proc.write_fd = os.open(os.devnull, os.O_WRONLY)
        with self.assertRaises(TimeoutError):
            refresh.buffered_rpc_request(self.proc, 9, 'x', timeout=1)


if __name__ == '__main__':
    unittest.main()
