#!/usr/bin/env python3
"""Offline, non-destructive copy of a server data directory into SQLCipher storage."""
import argparse
from contextlib import closing
import os
from pathlib import Path
import secrets
import shutil
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--key-file', type=Path, required=True)
    parser.add_argument('--generate-key', action='store_true')
    parser.add_argument('--decrypt', action='store_true', help='Explicitly create a new plaintext destination')
    args = parser.parse_args()
    if args.generate_key:
        fd = os.open(args.key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as out:
            out.write(secrets.token_hex(32)+'\n')
        return
    if not args.source or not args.destination or not args.source.is_dir():
        parser.error('--source and --destination are required for migration')
    source, target = args.source.resolve(), args.destination.resolve()
    if target == source or source in target.parents or target.exists():
        parser.error('Destination must be a new directory outside the source directory')
    # Configure before importing storage. The key is never passed on a command line.
    os.environ['DATA_ENCRYPTION_KEY_FILE'] = str(args.key_file.resolve())
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import storage
    cipher = storage.sqlite3
    target.mkdir(mode=0o700, parents=True)
    try:
        files = list(source.rglob('*'))
        if any(p.is_symlink() for p in files):
            raise ValueError('Symlinks are not allowed in the migration source')
        for path in files:
            if not path.is_file() or path.name.endswith(('-wal','-shm','-journal')) or path.name == '.gitkeep':
                continue
            if path.suffix not in ('.sqlite3','.db'):
                raise ValueError('Unexpected non-database file; move it out before migration: '+str(path.relative_to(source)))
            dest = target / path.relative_to(source)
            dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with closing(cipher.connect(str(path))) as con:
                if args.decrypt:
                    con.execute('PRAGMA key = '+chr(34)+"x'"+storage.KEY+"'"+chr(34))
                con.execute('SELECT count(*) FROM sqlite_master').fetchone()
                con.execute('ATTACH DATABASE ? AS encrypted KEY ?', (str(dest), "" if args.decrypt else "x'"+storage.KEY+"'"))
                con.execute("SELECT sqlcipher_export('encrypted')").fetchone()
                version = con.execute('PRAGMA user_version').fetchone()[0]
                con.execute('PRAGMA encrypted.user_version='+str(int(version)))
                con.execute('DETACH DATABASE encrypted')
            os.chmod(dest, 0o600)
            with closing(storage.plain_sqlite.connect(dest) if args.decrypt else storage.connect(dest)) as con:
                if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Encrypted database integrity check failed')
        if not any(target.rglob('*.sqlite3')) and not any(target.rglob('*.db')):
            raise ValueError('No databases found')
    except Exception:
        shutil.rmtree(target)
        raise


if __name__ == '__main__':
    main()
