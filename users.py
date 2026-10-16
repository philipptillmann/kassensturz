"""Local accounts; financial databases are isolated by server-generated storage keys."""
import hashlib
import re
import secrets
from pathlib import Path
from werkzeug.security import generate_password_hash
import app as ledger
from datasets import prepare_demo


def init(db):
    with ledger.connect(db) as con:
        con.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0, data_key TEXT NOT NULL, owns_legacy INTEGER NOT NULL DEFAULT 0)')
        if 'user_id' not in {r[1] for r in con.execute('PRAGMA table_info(sessions)')}:
            con.execute('ALTER TABLE sessions ADD COLUMN user_id INTEGER REFERENCES users(id)')


def version(user):
    return hashlib.sha256(user['password_hash'].encode()).hexdigest()


def credentials(data):
    if not isinstance(data, dict):
        raise ValueError('Benutzerdaten als JSON-Objekt erwartet.')
    name = data.get('username', '')
    password = data.get('password', '')
    if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,39}', name.strip().lower()):
        raise ValueError('Benutzername: 3–40 Zeichen (a–z, 0–9, Punkt, Bindestrich, Unterstrich).')
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        raise ValueError('Das Passwort muss 12–1024 Zeichen enthalten.')
    return name.strip().lower(), generate_password_hash(password)


def paths(db, user):
    root = Path(db).parent
    if user is not None and not user['owns_legacy']:
        key = user['data_key']
        if not re.fullmatch('[a-f0-9]{32}', key):
            raise ValueError('Ungültiger Kontospeicher.')
        root = root / 'users' / key
    return {'private': Path(db) if user is None or user['owns_legacy'] else root / 'expenses.sqlite3', 'demo': root / 'demo.sqlite3'}


def create(db, data, migrate=False):
    name, password_hash = credentials(data)
    key = secrets.token_hex(16)
    with ledger.connect(db) as con:
        con.execute('BEGIN IMMEDIATE')
        if migrate and con.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            raise ValueError('Die Daten wurden bereits einem Konto zugeordnet.')
        if con.execute('SELECT 1 FROM users WHERE username=?', (name,)).fetchone():
            raise ValueError('Dieser Benutzername ist bereits vergeben.')
        if not migrate:
            folder = Path(db).parent / 'users' / key
            folder.mkdir(parents=True, mode=0o700)
            ledger.init(folder / 'expenses.sqlite3')
            prepare_demo(folder / 'demo.sqlite3')
        con.execute('INSERT INTO users(username,password_hash,is_admin,data_key,owns_legacy) VALUES (?,?,?,?,?)', (name,password_hash,int(migrate),key,int(migrate)))
        if migrate:
            con.execute('DELETE FROM sessions')


def public(user):
    return {key: user[key] for key in ('id', 'username', 'is_admin')} if user else None


if __name__ == '__main__':
    import argparse
    import getpass
    parser = argparse.ArgumentParser(description='Passwort eines lokalen Kontos zurücksetzen')
    parser.add_argument('username')
    args = parser.parse_args()
    password = getpass.getpass('Neues Passwort: ')
    if password != getpass.getpass('Passwort wiederholen: '):
        parser.error('Passwörter stimmen nicht überein.')
    name, hashed = credentials({'username': args.username, 'password': password})
    with ledger.connect() as con:
        row = con.execute('SELECT id FROM users WHERE username=?', (name,)).fetchone()
        if not row:
            parser.error('Benutzer nicht gefunden.')
        con.execute('UPDATE users SET password_hash=? WHERE id=?', (hashed,row['id']))
        con.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))
    print('Passwort geändert; bestehende Sitzungen wurden beendet.')
