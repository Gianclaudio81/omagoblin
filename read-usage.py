#!/usr/bin/env python3
"""Read local agent usage records; stdout is a bounded JSON envelope."""
import json
import math
import os
import re
import signal
import stat
import sys

MAX_ENTRIES = 1024
MAX_FILES = 32
MAX_FILE_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 1024 * 1024
MAX_NODES = 16384
MAX_CONTAINER = 4096
MAX_DEPTH = 12
MAX_STRING = 4096
FORBIDDEN_KEYS = {"__proto__", "constructor", "prototype"}
AGENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate(value):
    nodes = 0

    def visit(item, depth=0):
        nonlocal nodes
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise ValueError("complexity")
        if isinstance(item, (dict, list)):
            if len(item) > MAX_CONTAINER:
                raise ValueError("cardinality")
            if isinstance(item, dict):
                for key, child in item.items():
                    if len(key) > 128 or key in FORBIDDEN_KEYS:
                        raise ValueError("key")
                    visit(child, depth + 1)
            else:
                for child in item:
                    visit(child, depth + 1)
        elif isinstance(item, str) and len(item) > MAX_STRING:
            raise ValueError("string")
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError("number")

    visit(value)
    if not isinstance(value, dict):
        raise ValueError("record")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def trusted(info, uid):
    return stat.S_ISREG(info.st_mode) and info.st_uid == uid and info.st_size <= MAX_FILE_BYTES


def scan(directory):
    uid = os.getuid()
    records = []
    rejected = 0
    limited = False
    files = total_bytes = 0
    try:
        dirfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        # No collector has run yet: nothing to show, not an error.
        return {"records": records, "rejected": rejected, "limited": limited}
    try:
        info = os.fstat(dirfd)
        if info.st_uid != uid or info.st_mode & stat.S_IWOTH:
            raise ValueError("usage directory ownership")
        # Streaming enumeration: never glob/sort an unbounded directory.
        with os.scandir(dirfd) as entries:
            for index, entry in enumerate(entries):
                if index >= MAX_ENTRIES:
                    limited = True
                    break
                if not entry.name.endswith(".json"):
                    continue
                agent_id = entry.name[:-5]
                if not AGENT_ID.match(agent_id):
                    rejected += 1
                    continue
                if files >= MAX_FILES or total_bytes >= MAX_TOTAL_BYTES:
                    limited = True
                    break
                files += 1  # Invalid files consume the budget too.
                try:
                    if not trusted(entry.stat(follow_symlinks=False), uid):
                        raise ValueError("file type, owner or size")
                    # Relative to the pinned directory; O_NOFOLLOW closes the
                    # stat/open symlink race, O_NONBLOCK avoids a swapped FIFO.
                    fd = os.open(entry.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dirfd)
                    with os.fdopen(fd, "rb") as stream:
                        info = os.fstat(stream.fileno())
                        if not trusted(info, uid):
                            raise ValueError("file type, owner or size")
                        allowance = min(MAX_FILE_BYTES + 1, MAX_TOTAL_BYTES - total_bytes)
                        raw = stream.read(allowance)
                    total_bytes += len(raw)
                    if len(raw) > MAX_FILE_BYTES or info.st_size > len(raw):
                        raise ValueError("size budget")
                    value = json.loads(raw, object_pairs_hook=unique_object)
                    validate(value)
                    records.append({"agentId": agent_id, "record": value})
                except (OSError, ValueError, OverflowError, RecursionError, UnicodeDecodeError):
                    rejected += 1
    finally:
        os.close(dirfd)
    records.sort(key=lambda item: item["agentId"])
    return {"records": records, "rejected": rejected, "limited": limited}


def main():
    # A stalled filesystem must not leave the read running indefinitely.
    signal.alarm(5)
    try:
        result = scan(sys.argv[1])
        sys.stdout.write(json.dumps(result, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n")
        return 0
    except (OSError, ValueError, IndexError, MemoryError, RecursionError):
        # Never echo file names or contents back into the shell log.
        sys.stderr.write("Usage record read failed\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
