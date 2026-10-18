import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import app
import backups


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'private.sqlite3'
        app.init(self.db)
        self.csv = dict(text='Date;Name;Amount\n2026-10-01;Cafe;-5,00\n', date_column='Date', merchant_column='Name', amount_column='Amount', payment_method='Bar')
        app.import_csv(self.csv, self.db)
        self.id = app.save_transaction(dict(date='2026-10-02',merchant='Gift',amount='80',category='Shopping',payment_method='PayPal',notes='Retain notes',group_name='Gift',items=[dict(name='Gift',amount='50',category='Shopping',group_name='Gift'),dict(name='Own',amount='30',category='Freizeit',group_name='')]), self.db)['id']
        with app.connect(self.db) as con:
            con.execute('INSERT INTO receipt_images VALUES (?,?)', (self.id,b'\xff\xd8receipt\xff\xd9'))
            con.execute("INSERT INTO account_settings VALUES ('PayPal',5000,1,'')")
            con.execute("INSERT INTO sessions VALUES ('session','csrf',9999999999,'version')")
            con.execute('CREATE TABLE users(username TEXT,password_hash TEXT)')
            con.execute("INSERT INTO users VALUES ('owner','do-not-export')")
        app.rename_category('Shopping', 'Einkäufe', self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def snapshot(self):
        with app.connect(self.db) as con:
            return {table: sorted([tuple(r) for r in con.execute('SELECT * FROM '+table)], key=repr) for table in backups.TABLES}

    def archive(self):
        output = io.BytesIO()
        backups.write_archive(self.db, output, dataset='private')
        return output.getvalue()

    def change_archive(self, raw, mutate=lambda m:m, extra=None, omit=None):
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw)) as source, zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as target:
            meta = json.loads(source.read('data.json'))
            mutate(meta)
            target.writestr('data.json', json.dumps(meta))
            for name in source.namelist()[1:]:
                if name != omit:
                    target.writestr(name, source.read(name))
            if extra:
                target.writestr(*extra)
        return output.getvalue()

    def test_roundtrip_preserves_financial_data_aliases_keys_and_auth(self):
        before = self.snapshot()
        raw = self.archive()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertNotIn(b'do-not-export', archive.read('data.json'))
            self.assertNotIn(b'"sessions"', archive.read('data.json'))
        summary = backups.preview(io.BytesIO(raw))
        self.assertEqual((summary['entries'],summary['receipts'],summary['dataset']), (2,1,'private'))
        self.assertEqual(before,self.snapshot())
        with app.connect(self.db) as con:
            con.execute('DELETE FROM transactions')
        backups.restore(io.BytesIO(raw), self.db)
        app.init(self.db)
        self.assertEqual(before,self.snapshot())
        self.assertEqual(app.preview_import(self.csv,self.db)['skipped'],1)
        with app.connect(self.db) as con:
            self.assertEqual(con.execute('SELECT username,password_hash FROM users').fetchone()[0],'owner')
            self.assertEqual(con.execute('SELECT token_hash FROM sessions').fetchone()[0],'session')
            self.assertIsNone(con.execute("SELECT 1 FROM categories WHERE name='Shopping'").fetchone())

    def test_invalid_archives_never_change_live_data(self):
        raw,before = self.archive(),self.snapshot()
        changes = [
            lambda m:m.update(version=99),
            lambda m:m['entries'][0].update(id=True),
            lambda m:m['entries'][0].update(amount=1.5),
            lambda m:m['entries'][0].update(category='Missing'),
            lambda m:m['entries'][0]['parts'][0].update(amount=1),
            lambda m:m['accounts'][0].update(share=10001),
            lambda m:m['accounts'][0].update(share_income='yes'),
            lambda m:m['server_aliases'].update(Shopping='Missing'),
            lambda m:m['transfers'].append(dict(outgoing=1,incoming=99)),
            lambda m:m['entries'].append(m['entries'][0]),
        ]
        invalid = [self.change_archive(raw,mutate) for mutate in changes]
        invalid += [b'not a zip', self.change_archive(raw,extra=('../escape',b'bad')),
                    self.change_archive(raw,omit=f'receipts/{self.id}.jpg')]
        for payload in invalid:
            with self.subTest(size=len(payload)):
                with self.assertRaises(ValueError):
                    backups.restore(io.BytesIO(payload),self.db)
                self.assertEqual(before,self.snapshot())

    def test_duplicate_receipts_and_limits_are_rejected(self):
        raw,before = self.archive(),self.snapshot()
        duplicate = self.change_archive(raw,extra=(f'receipts/{self.id}.jpg',b'\xff\xd8extra'))
        with self.assertRaises(ValueError):
            backups.preview(io.BytesIO(duplicate))
        with patch.object(backups,'MAX_RECEIPT',3):
            with self.assertRaises(ValueError):
                backups.restore(io.BytesIO(raw),self.db)
        with patch.object(backups,'MAX_METADATA',10):
            with self.assertRaises(ValueError):
                backups.preview(io.BytesIO(raw))
        self.assertEqual(before,self.snapshot())

    def test_target_insert_failure_rolls_back_replacement(self):
        raw,before = self.archive(),self.snapshot()
        with app.connect(self.db) as con:
            con.execute("CREATE TRIGGER prevent_insert BEFORE INSERT ON transactions BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(ValueError):
            backups.restore(io.BytesIO(raw),self.db)
        self.assertEqual(before,self.snapshot())

    def test_native_archive_without_server_extras_is_accepted(self):
        def native(meta):
            del meta['server_aliases']
            del meta['dataset']
            del meta['created_at']
            for entry in meta['entries']:
                for part in entry['parts']:
                    del part['id']
        raw = self.change_archive(self.archive(),native)
        self.assertEqual(backups.preview(io.BytesIO(raw))['dataset'],'unknown')
        backups.restore(io.BytesIO(raw),self.db)
        with app.connect(self.db) as con:
            self.assertEqual(con.execute("SELECT category FROM transactions WHERE merchant='Gift'").fetchone()[0],'Einkäufe')
            self.assertIsNotNone(con.execute("SELECT name FROM category_aliases WHERE alias='Unkategorisiert'").fetchone())

    def test_confirmed_and_ignored_transfers_roundtrip(self):
        out = app.save_transaction(dict(date='2026-10-03',merchant='Umbuchung',amount='15',category='Freizeit',payment_method='Bar'),self.db)['id']
        inc = app.save_transaction(dict(date='2026-10-03',merchant='Umbuchung',amount='-15',category='Freizeit',payment_method='PayPal'),self.db)['id']
        with app.connect(self.db) as con:
            con.execute("INSERT INTO account_settings VALUES ('Bar',10000,1,'')")
            con.execute('INSERT INTO transfer_links VALUES (?,?,0)',(out,inc))
            con.execute('INSERT INTO transfer_ignored VALUES (?,?)',(self.id,1))
        before,raw = self.snapshot(),self.archive()
        backups.restore(io.BytesIO(raw),self.db)
        self.assertEqual(before,self.snapshot())
