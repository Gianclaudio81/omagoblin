#!/usr/bin/env python3
"""Reuse Omarchy's collector with bounded retries and visible stale limits."""
import json
import os
import runpy
import time
from pathlib import Path


def guarded_collect(module, access_token, expires_at_ms, force):
    original = module['collect_limits']
    scope = original.__globals__
    probe = scope['probe_limits']
    cache = module['cache_root']() / 'omagoblin-claude-backoff.json'
    state = module['read_fresh_json'](cache, float('inf')) or {}
    now = time.time()
    failure = {}

    def guarded_probe(token):
        nonlocal failure
        if now < state.get('retryAt', 0):
            failure = {'ok': False, 'helpText': state.get('helpText', '')}
            return failure
        result = probe(token)
        if not result.get('ok'):
            failure = result
            if 'rate limiting' in result.get('helpText', ''):
                delay = min(1800, max(300, state.get('delay', 150) * 2))
                module['write_json'](cache, {'retryAt': now + delay, 'delay': delay,
                                            'helpText': result.get('helpText', '')})
        elif state:
            module['write_json'](cache, {})
        return result

    scope['probe_limits'] = guarded_probe
    try:
        result = original(access_token, expires_at_ms, force)
    finally:
        scope['probe_limits'] = probe
    if failure:
        result['usageStatusText'] = 'Claude limits outdated' if result['limits'] else 'Claude limits unavailable'
        result['authHelpText'] = failure.get('helpText', '') + ' Automatic retries use a cooldown.'
        # Our regular refresh handles failures without a rapid retry loop.
        result.pop('retryAdvised', None)
    return result


def main():
    collector = Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy')) / 'bin/omarchy-agent-usage-claude'
    module = runpy.run_path(str(collector))
    module['main'].__globals__['collect_limits'] = lambda token, expiry, force: guarded_collect(module, token, expiry, force)
    # The host main prints its display record; capture it for atomic publication.
    import contextlib
    import io
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        module['main']()
    record = json.loads(output.getvalue())
    target = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'omarchy/agents/usage'
    target.mkdir(parents=True, exist_ok=True)
    module['write_json'](target / 'claude.json', record)


if __name__ == '__main__':
    main()
