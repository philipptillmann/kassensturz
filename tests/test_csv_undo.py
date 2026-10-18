import concurrent.futures
import io
import tempfile
import unittest
from pathlib import Path
import app
import backups

class CsvUndoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'private.db';app.init(self.db)
    def tearDown(self): self.tmp.cleanup()
    def data(self, *names):
        return dict(text='Date;Name;Amount\n'+''.join(f'2026-10-01;{n};-5,00\n' for n in names),date_column='Date',merchant_column='Name',amount_column='Amount',payment_method='Bar')
    def ids(self):
        with app.connect(self.db) as c: return {r['merchant']:r['id'] for r in c.execute('SELECT * FROM transactions')}
    def test_latest_only_duplicates_manual_entries_and_restart(self):
        app.import_csv(self.data('Old'),self.db)
        app.save_transaction(dict(date='2026-10-01',merchant='Manual',amount='5',category='Shopping'),self.db)
        app.import_csv(self.data('Old','New'),self.db)
        batch=app.last_csv_import(self.db);self.assertEqual(batch['count'],1)
        app.init(self.db)
        self.assertEqual(app.last_csv_import(self.db),batch)
        self.assertEqual(app.revert_csv_import(batch['token'],self.db),{'removed':1})
        self.assertEqual(set(self.ids()),{'Old','Manual'})
        self.assertIsNone(app.last_csv_import(self.db)['token'])
        with self.assertRaises(ValueError): app.revert_csv_import(batch['token'],self.db)
        self.assertEqual(app.import_csv(self.data('New'),self.db)['added'],1)
    def test_failed_duplicate_and_preview_imports_preserve_undo(self):
        app.import_csv(self.data('First'),self.db);batch=app.last_csv_import(self.db)
        app.import_csv(self.data('First'),self.db)
        app.preview_import(self.data('Other'),self.db)
        bad=self.data('Other');bad['text']+='bad;Invalid;nope\n'
        with self.assertRaises(ValueError): app.import_csv(bad,self.db)
        self.assertEqual(app.last_csv_import(self.db),batch)
        app.import_csv(self.data('Next'),self.db)
        with self.assertRaises(ValueError): app.revert_csv_import(batch['token'],self.db)
        self.assertEqual(set(self.ids()),{'First','Next'})
    def test_edits_receipts_items_transfer_links_and_deleted_id_reuse(self):
        app.import_csv(self.data('Imported','Deleted'),self.db);ids=self.ids()
        with app.connect(self.db) as c:
            c.execute('UPDATE transactions SET merchant=?,amount=? WHERE id=?',('Edited',600,ids['Imported']))
            c.execute('INSERT INTO receipt_images VALUES (?,?)',(ids['Imported'],b'image'))
            c.execute('INSERT INTO items(transaction_id,name,amount,category) VALUES (?,?,?,?)',(ids['Imported'],'Part',600,'Shopping'))
            c.execute('DELETE FROM transactions WHERE id=?',(ids['Deleted'],))
        manual=app.save_transaction(dict(date='2026-10-01',merchant='Manual',amount='-6',category='Shopping'),self.db)['id']
        with app.connect(self.db) as c: c.execute('INSERT INTO transfer_links VALUES (?,?,1)',(ids['Imported'],manual))
        self.assertEqual(app.revert_csv_import(app.last_csv_import(self.db)['token'],self.db)['removed'],1)
        self.assertEqual(set(self.ids()),{'Manual'})
        with app.connect(self.db) as c:
            for table in ('items','receipt_images','transfer_links'): self.assertEqual(c.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
    def test_restore_clears_undo_and_datasets_are_independent(self):
        app.import_csv(self.data('First'),self.db);batch=app.last_csv_import(self.db)
        other=Path(self.tmp.name)/'demo.db';app.init(other)
        with self.assertRaises(ValueError): app.revert_csv_import(batch['token'],other)
        out=io.BytesIO();backups.write_archive(self.db,out,dataset='private')
        backups.restore(io.BytesIO(out.getvalue()),self.db)
        self.assertIsNone(app.last_csv_import(self.db)['token'])
        self.assertEqual(set(self.ids()),{'First'})
    def test_concurrent_revert_consumes_once(self):
        app.import_csv(self.data('First'),self.db);token=app.last_csv_import(self.db)['token']
        def revert(_):
            try:return app.revert_csv_import(token,self.db)['removed']
            except ValueError:return -1
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sorted(pool.map(revert,range(2))),[-1,1])
