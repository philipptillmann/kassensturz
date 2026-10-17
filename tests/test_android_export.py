import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as ledger
import users

spec = importlib.util.spec_from_file_location('android_export', Path(__file__).resolve().parents[1] / 'tools/export_android.py')
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


class AndroidExportTests(unittest.TestCase):
    def test_only_selected_account_and_no_credentials_are_exported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / 'expenses.sqlite3'
            ledger.init(db)
            users.init(db)
            users.create(db, {'username': 'owner', 'password': 'owner-password-long-enough'}, migrate=True)
            users.create(db, {'username': 'other', 'password': 'other-password-long-enough'})
            other_db = exporter.source_database(root, 'other')
            ledger.save_transaction({'merchant': 'Owner secret', 'date': '2026-10-01', 'amount': '12', 'category': 'Shopping'}, db=db)
            ledger.save_transaction({'merchant': 'Other gift', 'date': '2026-10-01', 'amount': '50', 'category': 'Shopping', 'notes': 'Retain note', 'items': [{'name': 'Gift', 'amount': '30', 'category': 'Shopping', 'group_name': 'Gift'}, {'name': 'Own', 'amount': '20', 'category': 'Freizeit', 'group_name': ''}]}, db=other_db)
            with ledger.connect(other_db) as con:
                con.execute('INSERT INTO receipt_images VALUES (?,?)', (1, b'\xff\xd8receipt'))
            output = root / 'phone.zip'
            self.assertEqual(exporter.export(other_db, output), (1, 1))
            with zipfile.ZipFile(output) as archive:
                meta = json.loads(archive.read('data.json'))
                self.assertNotIn('Owner secret', archive.read('data.json').decode())
                self.assertNotIn('password', archive.read('data.json').decode())
                self.assertNotIn('sessions', meta)
                self.assertEqual(meta['entries'][0]['notes'], 'Retain note')
                self.assertEqual(meta['entries'][0]['parts'][0]['group'], 'Gift')
                self.assertEqual(archive.read('receipts/1.jpg'), b'\xff\xd8receipt')
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                exporter.export(other_db, output)
            self.assertTrue(output.exists())
            with self.assertRaises(ValueError):
                exporter.source_database(root, legacy=True)
            with self.assertRaises(ValueError):
                exporter.source_database(root, username='missing')

    def test_legacy_export_is_explicit_and_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger.init(root / 'expenses.sqlite3')
            with self.assertRaises(ValueError):
                exporter.source_database(root, username='owner')
            source = exporter.source_database(root, legacy=True)
            self.assertEqual(source, root / 'expenses.sqlite3')
            exporter.export(source, root / 'legacy.zip')
            with ledger.connect(source) as con:
                self.assertEqual(con.execute('SELECT count(*) FROM transactions').fetchone()[0], 0)
