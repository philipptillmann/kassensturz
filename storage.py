"""Optional whole-database SQLCipher storage. No silent fallback or conversion."""
import os
from pathlib import Path
import re
import stat
import tempfile
import sqlite3 as plain_sqlite

KEY_FILE = os.environ.get('DATA_ENCRYPTION_KEY_FILE', '')
KEY = None
sqlite3 = plain_sqlite
if KEY_FILE:
    path = Path(KEY_FILE)
    if os.name == 'posix' and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise RuntimeError('Encryption key file must not be readable by group/others (mode 0600 or 0400).')
    KEY = path.read_text(encoding='ascii').strip()
    if not re.fullmatch(r'[0-9a-fA-F]{64}', KEY):
        raise RuntimeError('Encryption key file must contain exactly 64 hexadecimal characters.')
    try:
        from sqlcipher3 import dbapi2 as sqlite3
    except ImportError as error:
        raise RuntimeError('Encrypted storage requires sqlcipher3; no plaintext fallback is allowed.') from error


def connect(path, **kwargs):
    con = sqlite3.connect(path, **kwargs)
    try:
        if KEY:
            if not con.execute('PRAGMA cipher_version').fetchone():
                raise RuntimeError('SQLCipher support is unavailable.')
            con.execute('PRAGMA key = "x\'' + KEY + '\'"')
            con.execute('PRAGMA cipher_memory_security=ON')
        con.execute('PRAGMA temp_store=MEMORY')
        # Fail before modifying an existing database if key/mode is wrong.
        con.execute('SELECT count(*) FROM sqlite_master').fetchone()
        con.row_factory = sqlite3.Row
        return con
    except Exception:
        con.close()
        raise


def attach(con, path, alias='restored'):
    if alias != 'restored':
        raise ValueError('Unsupported attachment name.')
    if KEY:
        con.execute('ATTACH DATABASE ? AS restored KEY ?', (str(path), "x'" + KEY + "'"))
    else:
        con.execute('ATTACH DATABASE ? AS restored', (str(path),))


def temporary_directory(default=None):
    """Unencrypted archive/OCR scratch must be on explicitly provisioned RAM storage."""
    if not KEY:
        return default
    folder = os.environ.get('ENCRYPTED_TMPDIR')
    if not folder or not Path(folder).is_dir():
        raise RuntimeError('Set ENCRYPTED_TMPDIR to a RAM-backed directory before enabling encryption.')
    # Linux deployment must prove RAM backing rather than trust an arbitrary path.
    if os.name == 'posix' and Path('/proc/mounts').exists():
        resolved = Path(folder).resolve()
        matches = []
        for line in Path('/proc/mounts').read_text().splitlines():
            parts = line.split()
            mount = Path(parts[1].replace('\\040', ' '))
            if resolved == mount or mount in resolved.parents:
                matches.append((len(str(mount)), parts[2]))
        if not matches or max(matches)[1] not in ('tmpfs','ramfs'):
            raise RuntimeError('ENCRYPTED_TMPDIR must be on tmpfs/ramfs, not persistent disk.')
    return folder
