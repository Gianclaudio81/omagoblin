#!/usr/bin/env python3
"""Read untrusted synced snapshots; stdout is a bounded JSON envelope."""
import json
import math
import os
import signal
import stat
import sys

MAX_ENTRIES = 1024
MAX_FILES = 64
MAX_FILE_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_NODES = 8192
MAX_TOTAL_NODES = 32768
MAX_CONTAINER = 4096
MAX_DEPTH = 12
MAX_STRING = 256
FORBIDDEN_KEYS = {"__proto__", "constructor", "prototype"}


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
        elif isinstance(item, (int, float)) and (not math.isfinite(item) or abs(item) > 1e15):
            raise ValueError("number")

    visit(value)
    if not isinstance(value, dict) or not isinstance(value.get("providers"), dict):
        raise ValueError("snapshot")
    if not isinstance(value.get("deviceId", "device"), str):
        raise ValueError("device")
    if len(value["providers"]) > 32:
        raise ValueError("providers")
    for stats in value["providers"].values():
        if not isinstance(stats, dict):
            raise ValueError("provider")
        for field in ("todayTokensByModel", "modelUsage"):
            if not isinstance(stats.get(field, {}), dict):
                raise ValueError("model map")
        for bucket in stats.get("modelUsage", {}).values():
            if not isinstance(bucket, dict):
                raise ValueError("bucket")
        for field in ("activeDates", "recentDays"):
            if not isinstance(stats.get(field, []), list):
                raise ValueError("dates")
    return nodes


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def scan(directory):
    snapshots = []
    rejected = 0
    limited = False
    files = total_bytes = total_nodes = 0
    # Reserve ample space for envelope fields and separators.
    output_bytes = 128
    dirfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        # Streaming enumeration: never glob/sort an unbounded directory.
        with os.scandir(dirfd) as entries:
            for index, entry in enumerate(entries):
                if index >= MAX_ENTRIES:
                    limited = True
                    break
                if not entry.name.endswith(".json"):
                    continue
                if files >= MAX_FILES or total_bytes >= MAX_TOTAL_BYTES:
                    limited = True
                    break
                files += 1  # Invalid files consume the budget too.
                try:
                    info = entry.stat(follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
                        raise ValueError("file type or size")
                    # Relative to the pinned directory; O_NOFOLLOW closes the
                    # stat/open symlink race, O_NONBLOCK avoids a swapped FIFO.
                    fd = os.open(entry.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dirfd)
                    with os.fdopen(fd, "rb") as stream:
                        info = os.fstat(stream.fileno())
                        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
                            raise ValueError("file type or size")
                        allowance = min(MAX_FILE_BYTES + 1, MAX_TOTAL_BYTES - total_bytes)
                        raw = stream.read(allowance)
                    total_bytes += len(raw)
                    if len(raw) > MAX_FILE_BYTES or info.st_size > len(raw):
                        raise ValueError("size budget")
                    value = json.loads(raw, object_pairs_hook=unique_object)
                    nodes = validate(value)
                    if total_nodes + nodes > MAX_TOTAL_NODES:
                        limited = True
                        break
                    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
                    if output_bytes + len(encoded) + 1 > MAX_OUTPUT_BYTES:
                        limited = True
                        break
                    total_nodes += nodes
                    output_bytes += len(encoded) + 1
                    snapshots.append(value)
                except (OSError, ValueError, OverflowError, RecursionError):
                    rejected += 1
    finally:
        os.close(dirfd)
    return {"snapshots": snapshots, "rejected": rejected, "limited": limited}


def main():
    # A stalled filesystem must not leave the scan running indefinitely.
    signal.alarm(5)
    try:
        result = scan(sys.argv[1])
        output = json.dumps(result, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n"
        if len(output) > MAX_OUTPUT_BYTES:
            return 1
        sys.stdout.write(output)
        return 0
    except (OSError, ValueError, IndexError, MemoryError, RecursionError):
        # Never echo attacker-controlled filenames/data into a collector.
        sys.stderr.write("Usage sync scan failed\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
