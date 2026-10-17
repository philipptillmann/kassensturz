#!/usr/bin/env python3
"""Export one server dataset to an Android backup without authentication records.

Run as the server operator against a local data directory or a complete backup.
Only Python's standard library is required. Source databases are read-only.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import zipfile


def connect(path):
    con = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    return con


def source_database(root, username=None, legacy=False, dataset='private'):
    root = Path(root)
    auth_db = root / 'expenses.sqlite3'
    with connect(auth_db) as con:
        exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
        has_users = exists and con.execute('SELECT 1 FROM users LIMIT 1').fetchone()
        if legacy:
            if has_users:
                raise ValueError('Named accounts exist; select --username instead of --legacy.')
            folder = root
        else:
            if not has_users:
                raise ValueError('No named accounts exist. Use --legacy for the original dataset.')
            row = con.execute('SELECT data_key,owns_legacy FROM users WHERE username=?', (username.strip().lower(),)).fetchone()
            if row is None:
                raise ValueError('Account not found.')
            if row['owns_legacy']:
                folder = root
            else:
                if not re.fullmatch('[a-f0-9]{32}', row['data_key']):
                    raise ValueError('Invalid account storage key.')
                folder = root / 'users' / row['data_key']
    return folder / ('expenses.sqlite3' if dataset == 'private' else 'demo.sqlite3')


def export(source, output):
    output = Path(output)
    created = False
    try:
        with connect(source) as con:
            con.execute('BEGIN')  # One consistent snapshot, including WAL and receipt blobs.
            categories = [r[0] for r in con.execute('SELECT name FROM categories ORDER BY name')]
            payments = [r[0] for r in con.execute('SELECT name FROM payment_methods ORDER BY name')]
            parts = {}
            for row in con.execute('SELECT * FROM items ORDER BY id'):
                parts.setdefault(row['transaction_id'], []).append(dict(name=row['name'], amount=row['amount'], category=row['category'], group=row['group_name']))
            receipt_ids = {r[0] for r in con.execute('SELECT transaction_id FROM receipt_images')}
            receipt_size = con.execute('SELECT COALESCE(SUM(length(image)),0),COALESCE(MAX(length(image)),0) FROM receipt_images').fetchone()
            if receipt_size[0] > 512_000_000 or receipt_size[1] > 4_000_000:
                raise ValueError('Receipt images exceed the Android backup limits.')
            entries = []
            for row in con.execute('SELECT * FROM transactions ORDER BY date DESC,id DESC'):
                entries.append(dict(id=row['id'], date=row['date'], merchant=row['merchant'], amount=row['amount'], category=row['category'], payment=row['payment_method'], kind=row['kind'], notes=row['notes'], group=row['group_name'], parts=parts.get(row['id'], []), receipt=row['id'] in receipt_ids, counterparty=row['counterparty_iban'], import_key=row['import_key']))
            accounts = [dict(name=r['payment_method'], share=r['share_bp'], share_income=bool(r['share_income']), iban=r['iban']) for r in con.execute('SELECT * FROM account_settings')]
            def pairs(table):
                return [dict(outgoing=r['outgoing_id'], incoming=r['incoming_id']) for r in con.execute('SELECT outgoing_id,incoming_id FROM ' + table)]
            meta = dict(format='kassensturz-android', version=1, categories=categories, payments=payments, entries=entries, accounts=accounts, transfers=pairs('transfer_links'), ignored=pairs('transfer_ignored'))
            # A renamed server default is still represented by its category alias.
            if con.execute("SELECT 1 FROM category_aliases WHERE alias='Ausgehen'").fetchone():
                meta['category_defaults_version'] = 1
            encoded = json.dumps(meta, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            if len(encoded) > 16_000_000 or len(entries) > 50000 or len(categories) > 2000 or len(payments) > 2000:
                raise ValueError('Dataset exceeds the Android backup limits.')
            # Exclusive create: never overwrite an existing backup. Restrict before writing.
            fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            with os.fdopen(fd, 'wb') as file, zipfile.ZipFile(file, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('data.json', encoded)
                for row in con.execute('SELECT transaction_id,image FROM receipt_images ORDER BY transaction_id'):
                    archive.writestr(f"receipts/{row['transaction_id']}.jpg", row['image'])
            return len(entries), len(receipt_ids)
    except BaseException:
        if created:
            output.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', required=True, type=Path)
    owner = parser.add_mutually_exclusive_group(required=True)
    owner.add_argument('--username')
    owner.add_argument('--legacy', action='store_true')
    parser.add_argument('--dataset', choices=['private', 'demo'], default='private')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        source = source_database(args.data_dir, args.username, args.legacy, args.dataset)
        transactions, receipts = export(source, args.output)
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, f'Export failed: {error}\n')
    print(f'Exported {transactions} transactions and {receipts} receipts to {args.output}')


if __name__ == '__main__':
    main()
