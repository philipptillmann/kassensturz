import concurrent.futures
import tempfile
import unittest
from pathlib import Path

import app


class ImportPreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'private.sqlite3'
        app.init(self.db)
        self.data = dict(text='Datum;Name;Betrag\n01.10.2026;Cafe;-5,00\n01.10.2026;Cafe;-5,00\n',
                         date_column='Datum', merchant_column='Name', amount_column='Betrag', payment_method='Bar')

    def tearDown(self):
        self.tmp.cleanup()

    def test_preview_is_read_only_and_counts_real_occurrences(self):
        before = app.preview_import(self.data, self.db)
        self.assertEqual((before['added'], before['skipped']), (2, 0))
        self.assertEqual([row['duplicate'] for row in before['rows']], [False, False])
        with app.connect(self.db) as con:
            self.assertEqual(con.execute('SELECT count(*) FROM transactions').fetchone()[0], 0)
        self.assertEqual(app.import_csv(self.data, self.db), dict(added=2, skipped=0))
        after = app.preview_import(self.data, self.db)
        self.assertEqual((after['added'], after['skipped']), (0, 2))
        self.assertTrue(all(row['duplicate'] for row in after['rows']))

    def test_commit_rechecks_after_preview_and_concurrent_imports(self):
        self.assertEqual(app.preview_import(self.data, self.db)['added'], 2)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: app.import_csv(self.data, self.db), range(2)))
        self.assertEqual(sorted(row['added'] for row in results), [0, 2])
        self.assertEqual(sum(row['skipped'] for row in results), 2)

    def test_accounts_datasets_and_manual_lookalikes_are_independent(self):
        app.save_transaction(dict(date='2026-10-01', merchant='Cafe', amount='5', category='Freizeit', payment_method='Bar'), self.db)
        self.assertEqual(app.preview_import(self.data, self.db)['added'], 2)
        app.import_csv(self.data, self.db)
        self.assertEqual(app.preview_import({**self.data, 'payment_method': 'PayPal'}, self.db)['added'], 2)
        other = Path(self.tmp.name) / 'demo.sqlite3'
        app.init(other)
        self.assertEqual(app.preview_import(self.data, other)['added'], 2)

    def test_imported_entry_edits_keep_identity_and_invalid_preview_writes_nothing(self):
        app.import_csv(self.data, self.db)
        with app.connect(self.db) as con:
            con.execute("UPDATE transactions SET merchant='Edited description', amount=750")
        self.assertEqual(app.preview_import(self.data, self.db)['skipped'], 2)
        bad = {**self.data, 'text': self.data['text'] + 'bad;Cafe;-5,00\n'}
        with self.assertRaises(ValueError):
            app.preview_import(bad, self.db)
        with self.assertRaises(ValueError):
            app.import_csv(bad, self.db)
        with app.connect(self.db) as con:
            self.assertEqual(con.execute('SELECT count(*) FROM transactions').fetchone()[0], 2)
