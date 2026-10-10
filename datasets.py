"""Separate, persistent demo ledger; the original ledger remains private."""
import datetime
import json

import app as ledger


def prepare_demo(db):
    ledger.init(db)
    samples = json.loads((ledger.ROOT / 'sample-data' / 'demo.json').read_text())
    today = datetime.date.today()
    with ledger.connect(db) as con:
        con.execute('CREATE TABLE IF NOT EXISTS dataset_meta(key TEXT PRIMARY KEY)')
        seeded = {row[0] for row in con.execute('SELECT key FROM dataset_meta')}
        groups = set()
        # The seed and marker are one transaction, so a restart cannot duplicate data.
        for sample in samples:
            group = 'seeded' if not sample.get('seed_group') else 'seeded-' + sample['seed_group']
            if group in seeded:
                continue
            groups.add(group)
            month = today.year * 12 + today.month - 1 + sample['month_offset']
            year, month = divmod(month, 12)
            date = datetime.date(year, month + 1, sample['day']).isoformat()
            items = sample.get('items', [])
            amount = ledger.cents(sample['amount'])
            if items and sum(ledger.cents(item['amount']) for item in items) != amount:
                raise ValueError('Invalid demo split')
            txid = con.execute(
                'INSERT INTO transactions(date,merchant,amount,category) VALUES (?,?,?,?)',
                (date, sample['merchant'], amount, sample['category'])).lastrowid
            con.executemany('INSERT INTO items(transaction_id,name,amount,category) VALUES (?,?,?,?)',
                            [(txid, item['name'], ledger.cents(item['amount']), item['category']) for item in items])
        con.executemany('INSERT INTO dataset_meta VALUES (?)', [(group,) for group in sorted(groups)])
