#!/usr/bin/env python3
"""Publish this machine's sync snapshot without following planted links."""
import json
import os
import re
import secrets
import signal
import stat
import sys

MAX_SNAPSHOT_BYTES = 256 * 1024
FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\.json$")


def publish(directory, name, text):
    if not FILE_NAME.match(name):
        raise ValueError("file name")
    data = text.encode("utf-8")
    if len(data) > MAX_SNAPSHOT_BYTES:
        raise ValueError("snapshot size")
    if not isinstance(json.loads(data), dict):
        raise ValueError("snapshot")
    # The folder itself is the user's choice and may be a link to a mount;
    # only entries inside it can have been planted by a synced peer.
    dirfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        info = os.fstat(dirfd)
        if info.st_uid != os.getuid() or info.st_mode & stat.S_IWOTH:
            raise ValueError("sync directory ownership")
        temp = "." + name + "." + secrets.token_hex(8) + ".tmp"
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dirfd)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            # rename() replaces the directory entry itself: a symlink or FIFO
            # left at the target is swapped out, never written through.
            os.rename(temp, name, src_dir_fd=dirfd, dst_dir_fd=dirfd)
        except BaseException:
            try:
                os.unlink(temp, dir_fd=dirfd)
            except OSError:
                pass
            raise
    finally:
        os.close(dirfd)


def main():
    signal.alarm(5)
    try:
        publish(sys.argv[1], sys.argv[2], os.environ.get("OMAGOBLIN_SNAPSHOT", ""))
        return 0
    except (OSError, ValueError, IndexError, UnicodeError):
        sys.stderr.write("Usage sync write failed\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
