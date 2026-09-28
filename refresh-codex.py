#!/usr/bin/env python3
"""Reuse Omarchy's Codex collector with a buffer-aware app-server reader."""
import contextlib
import io
import json
import os
import runpy
import select
import time
from pathlib import Path

MAX_LINE_BYTES = 1024 * 1024


def buffered_rpc_request(proc, request_id, method, params=None, timeout=8):
    """Like the host rpc_request, but never loses lines already buffered.

    The host pairs select() on the pipe with readline() on the text wrapper:
    when a notification and the reply arrive in one chunk, the reply sits in
    Python's buffer, select() reports nothing and the request times out.
    """
    payload = {"id": request_id, "method": method, "params": params or {}}
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()
    pending = getattr(proc, "_omagoblin_pending", b"")
    fd = proc.stdout.fileno()
    deadline = time.time() + timeout
    try:
        while True:
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                if isinstance(message, dict) and message.get("id") == request_id:
                    return message
            if len(pending) > MAX_LINE_BYTES:
                raise TimeoutError(method)
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(method)
            ready, _, _ = select.select([fd], [], [], min(0.25, remaining))
            if not ready:
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                raise TimeoutError(method)
            pending += chunk
    finally:
        proc._omagoblin_pending = pending


def main():
    collector = Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy')) / 'bin/omarchy-agent-usage-codex'
    module = runpy.run_path(str(collector))
    scope = module['fetch_codex_rpc'].__globals__
    scope['rpc_request'] = buffered_rpc_request
    fetch = scope['fetch_codex_rpc']

    def fetch_with_retry():
        # One quick second attempt covers a slow app-server start.
        result = fetch()
        return result if result['limits'] else fetch()

    scope['fetch_codex_rpc'] = fetch_with_retry
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        module['main']()
    record = json.loads(output.getvalue())
    target = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'omarchy/agents/usage'
    target.mkdir(parents=True, exist_ok=True)
    module['write_json'](target / 'codex.json', record)


if __name__ == '__main__':
    main()
