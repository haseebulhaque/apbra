"""Test-local historical file universe; never used by runtime governance enumeration."""
import hashlib
from pathlib import Path, PurePosixPath
import subprocess

BASE = '3dfae4294334fa934223b8b1ab2654ffcc9c04f4'
TREE = '5822019569e83c2e5c80727d37d48c48a842836c'
UNIVERSE_SHA = 'b0ba6f6b98775312a6ae5e825fc150022c7ea75bb557373e1d586533f6bee88e'


def historical_names(source_root: Path, additions=()) -> set[str]:
    """Stage current bytes from the released H3 names plus explicit test additions.

    Resolve the immutable object each call. No current-file enumeration is
    changed, no cache/future-path denylist and no fixture file is silently skipped.
    The caller retains its ordinary copy and subsequent negative-mutation logic.
    """
    tree = subprocess.check_output(
        ['git', '-C', str(source_root), 'rev-parse', BASE + '^{tree}'], timeout=10, stderr=subprocess.PIPE
    ).decode('ascii').strip()
    if tree != TREE:
        raise ValueError('Historical fixture tree differs from released H3')
    raw = subprocess.check_output(
        ['git', '-C', str(source_root), 'ls-tree', '-rz', '--name-only', BASE], timeout=10, stderr=subprocess.PIPE
    )
    if hashlib.sha256(raw).hexdigest() != UNIVERSE_SHA:
        raise ValueError('Historical fixture pathname universe differs from H3')
    names = raw.decode('utf-8').split('\0')
    if not names or names[-1] != '':
        raise ValueError('Historical fixture pathname universe is malformed')
    names.pop()
    if len(set(names)) != len(names):
        raise ValueError('Historical fixture pathname universe contains duplicates')
    selected = set(names)
    for name in additions:
        if (type(name) is not str or not name or '\\' in name or
                PurePosixPath(name).is_absolute() or any(p in ('', '.', '..', '.git') for p in name.split('/'))):
            raise ValueError('Historical fixture explicit path is unsafe')
        selected.add(name)
    return selected
