#!/usr/bin/env python3
"""Repair Alpha's private state before its native security guard starts."""
import os
import stat
import sys
from pathlib import Path


PRIVATE_PATHS = ('.local/share/com.alpha.guard', '.local/state/alpha')


def secure_tree(path):
    # Explicit chmod is needed even after mkdir(mode=0700): NAS ACLs can
    # otherwise leave new directories with group/other permissions.
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        secure_directory(descriptor)
    finally:
        os.close(descriptor)


def secure_directory(descriptor):
    os.fchmod(descriptor, 0o700)
    with os.scandir(descriptor) as entries:
        for entry in entries:
            mode = entry.stat(follow_symlinks=False).st_mode
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                continue
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if stat.S_ISDIR(mode):
                flags |= os.O_DIRECTORY
            child = os.open(entry.name, flags, dir_fd=descriptor)
            try:
                if stat.S_ISDIR(os.fstat(child).st_mode):
                    secure_directory(child)
                else:
                    os.fchmod(child, 0o600)
            finally:
                os.close(child)


def prepare(home):
    for relative in PRIVATE_PATHS:
        secure_tree(home / relative)


if __name__ == '__main__':
    try:
        prepare(Path.home())
    except OSError as error:
        print(f'WeHarbor: cannot secure Alpha private state: {error}', file=sys.stderr)
        sys.exit(1)
