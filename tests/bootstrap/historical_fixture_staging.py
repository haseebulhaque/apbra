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


# New knowledge registration fixtures stage names from actual released H9.
KNOWLEDGE_REGISTRATION_BASE = '287ceac2c67979d60f45d44d0d0da21798f96dcd'
KNOWLEDGE_REGISTRATION_TREE = '76903c07688d79c1b9ca4fdfd98965b23433d54d'
KNOWLEDGE_REGISTRATION_UNIVERSE_SHA = '3dad0a31dd8add81398efcfa0edaa37e92f662662c838ab652441210c97c49b8'


def knowledge_registration_names(source_root: Path, additions=()) -> set[str]:
    """Copy current bytes only for pinned H9 names plus explicit test additions.

    Current runtime enumeration remains exhaustive. This only isolates three
    historical prospective fixtures from future product files they never owned.
    """
    try:
        tree = subprocess.check_output(
            ['git', '-C', str(source_root), 'rev-parse', KNOWLEDGE_REGISTRATION_BASE + '^{tree}'],
            timeout=10, stderr=subprocess.PIPE,
        ).decode('ascii').strip()
        if tree != KNOWLEDGE_REGISTRATION_TREE:
            raise ValueError('Knowledge fixture tree differs')
        raw = subprocess.check_output(
            ['git', '-C', str(source_root), 'ls-tree', '-rz', '--name-only', KNOWLEDGE_REGISTRATION_BASE],
            timeout=10, stderr=subprocess.PIPE,
        )
        if hashlib.sha256(raw).hexdigest() != KNOWLEDGE_REGISTRATION_UNIVERSE_SHA:
            raise ValueError('Knowledge fixture universe differs')
        names = raw.decode('utf-8').split('\0')
        if not names or names[-1] != '':
            raise ValueError('Knowledge fixture universe malformed')
        names.pop()
        if not names or len(set(names)) != len(names):
            raise ValueError('Knowledge fixture universe malformed')
        selected = set(names)
        for name in [*names, *additions]:
            if (type(name) is not str or not name or '\\' in name or '\0' in name or
                    PurePosixPath(name).is_absolute() or
                    any(part in ('', '.', '..', '.git') for part in name.split('/'))):
                raise ValueError('Knowledge fixture path unsafe')
            selected.add(name)
        return selected
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        raise ValueError('Knowledge historical fixture snapshot unavailable') from None


# New local document-draft registration isolates the released H12 journal evidence.
TENANT_DOCUMENT_DRAFTS_HISTORICAL_BASE = 'dfe9f65fd68ba6573d8fe0be11c1efd7974432fc'
TENANT_DOCUMENT_DRAFTS_HISTORICAL_TREE = '1f2aaba3ed82e89cd2cd1b71cf35e2b3876fb1e2'
TENANT_DOCUMENT_DRAFTS_HISTORICAL_UNIVERSE_SHA = '37fdb4858cd94fa339e7f013d28b399286f9fcbb0a9dfaf3bf1f00bd8fd09103'
TENANT_DOCUMENT_DRAFTS_HISTORICAL_SNAPSHOTS = {
    'scripts/check_bootstrap.py': (262076, '4cbaa8969739953dbe13bc47fae7a584fd7d562822e14fb834ba7b36a5c85674'),
    'tests/bootstrap/historical_fixture_staging.py': (4202, 'efe2b7b495e6d3e1f08043b7a4a4c5e14e887b5fa1a0fc1441cf224428013243'),
}


def document_drafts_registration_names(source_root: Path, additions=()) -> set[str]:
    """Current bytes for fixed H12 names plus explicit historical test additions.

    This is test-local staging only; current checker enumeration is unchanged.
    """
    try:
        tree = subprocess.check_output(
            ['git', '-C', str(source_root), 'rev-parse', TENANT_DOCUMENT_DRAFTS_HISTORICAL_BASE + '^{tree}'],
            timeout=10, stderr=subprocess.PIPE,
        ).decode('ascii').strip()
        if tree != TENANT_DOCUMENT_DRAFTS_HISTORICAL_TREE:
            raise ValueError('Historical tree differs')
        raw = subprocess.check_output(
            ['git', '-C', str(source_root), 'ls-tree', '-rz', '--name-only', TENANT_DOCUMENT_DRAFTS_HISTORICAL_BASE],
            timeout=10, stderr=subprocess.PIPE,
        )
        if hashlib.sha256(raw).hexdigest() != TENANT_DOCUMENT_DRAFTS_HISTORICAL_UNIVERSE_SHA:
            raise ValueError('Historical universe differs')
        names = raw.decode('utf-8').split('\0')
        if not names or names[-1] != '':
            raise ValueError('Historical universe malformed')
        names.pop()
        if not names or len(set(names)) != len(names):
            raise ValueError('Historical universe malformed')
        selected = set(names)
        for name in [*names, *additions]:
            if (type(name) is not str or not name or '\\' in name or '\0' in name or
                    PurePosixPath(name).is_absolute() or
                    any(part in ('', '.', '..', '.git') for part in name.split('/'))):
                raise ValueError('Historical path unsafe')
            selected.add(name)
        return selected
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        raise ValueError('Document draft historical fixture universe unavailable') from None


def knowledge_registration_snapshot(source_root: Path, path: str) -> bytes:
    """Verified released H12 bytes for the two old journal registration assertions."""
    try:
        if type(path) is not str or path not in TENANT_DOCUMENT_DRAFTS_HISTORICAL_SNAPSHOTS:
            raise ValueError('Historical snapshot path differs')
        size, expected = TENANT_DOCUMENT_DRAFTS_HISTORICAL_SNAPSHOTS[path]
        tree = subprocess.check_output(
            ['git', '-C', str(source_root), 'rev-parse', TENANT_DOCUMENT_DRAFTS_HISTORICAL_BASE + '^{tree}'],
            timeout=10, stderr=subprocess.PIPE,
        ).decode('ascii').strip()
        if tree != TENANT_DOCUMENT_DRAFTS_HISTORICAL_TREE:
            raise ValueError('Historical snapshot tree differs')
        raw = subprocess.check_output(
            ['git', '-C', str(source_root), 'show', TENANT_DOCUMENT_DRAFTS_HISTORICAL_BASE + ':' + path],
            timeout=10, stderr=subprocess.PIPE,
        )
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Historical snapshot bytes differ')
        return raw
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        raise ValueError('Knowledge registration historical snapshot unavailable') from None
