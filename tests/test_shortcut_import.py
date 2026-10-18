import concurrent.futures
import io
import json
import sqlite3
from pathlib import Path
import tempfile
import unittest

import app
import backups
import shortcut_api


class ShortcutImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'private.sqlite3'
        app.init(self.db)
        self.body = json.loads((app.ROOT/'docs/examples/shortcut-expense.json').read_text())

    def tearDown(self):
        self.tmp.cleanup()

    def count(self):
        with app.connect(self.db) as con:
            return con.execute('SELECT count(*) FROM transactions').fetchone()[0]

    def test_one_step_documented_example_timezone_totals_and_key_order_retry(self):
        body = {**self.body,'timestamp':'2026-10-18T00:15:00+02:00'}
        first,status = shortcut_api.ingest(body,self.db)
        self.assertEqual(status,201)
        again,status = shortcut_api.ingest(dict(reversed(list(body.items()))),self.db)
        self.assertEqual(status,200)
        self.assertEqual(first['id'],again['id'])
        self.assertEqual(first['entry_ids'],again['entry_ids'])
        self.assertTrue(again['duplicate'])
        self.assertEqual(self.count(),1)
        with app.connect(self.db) as con:
            row = con.execute('SELECT * FROM transactions').fetchone()
            self.assertEqual((row['date'],row['amount'],row['category'],row['payment_method']),('2026-10-18',2450,'Ausgehen','Bar'))
            self.assertEqual(json.loads(con.execute('SELECT payload FROM shortcut_imports').fetchone()[0]),body)

    def test_text_fences_originals_and_retries_after_category_and_entry_edits(self):
        raw = '```json\n'+json.dumps(self.body['ai'],ensure_ascii=False,indent=2)+'\n```'
        body = {**self.body,'ai':raw}
        first,_ = shortcut_api.ingest(body,self.db)
        app.rename_category('Ausgehen','Restaurant',self.db)
        with app.connect(self.db) as con:
            con.execute("UPDATE transactions SET merchant='Edited',amount=3000")
        retry,status = shortcut_api.ingest(body,self.db)
        self.assertEqual(status,200)
        self.assertEqual(retry['entry_ids'],first['entry_ids'])
        with app.connect(self.db) as con:
            self.assertEqual(tuple(con.execute('SELECT merchant,amount FROM transactions').fetchone()),('Edited',3000))
            self.assertEqual(json.loads(con.execute('SELECT payload FROM shortcut_imports').fetchone()[0])['ai'],raw)
        # Default-category aliases also work for a new request after a rename.
        new = {**self.body,'timestamp':'2026-10-18T19:30:00+02:00'}
        self.assertEqual(shortcut_api.ingest(new,self.db)[1],201)

    def test_invalid_payloads_write_neither_transaction_nor_source(self):
        variants = [
            {**self.body,'timestamp':'2026-10-18T12:00:00'},
            {**self.body,'timestamp':'2026-02-30T12:00:00Z'},
            {**self.body,'ai':'{bad json'},
            {**self.body,'ai':[]},
            {**self.body,'user_id':2},
        ]
        for changes in [{'amount':None},{'amount':True},{'amount':'NaN'},{'amount':'0.001'},{'amount':0},{'amount':'1000000000'},
                        {'currency':'USD'},{'category':'Missing'},{'payment_method':'Unknown'}, {'title':''},
                        {'date':'2026-01-01'},{'id':1},{'notes':'x'*2001},
                        {'items':[dict(name='Item',amount='2')]}]:
            variants.append({**self.body,'ai':{**self.body['ai'],**changes}})
        for body in variants:
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    shortcut_api.ingest(body,self.db)
                self.assertEqual(self.count(),0)
        with app.connect(self.db) as con:
            self.assertEqual(con.execute('SELECT count(*) FROM shortcut_imports').fetchone()[0],0)

    def test_split_refund_is_one_transaction_with_exact_signed_totals(self):
        ai=dict(title='Gift refund',amount='-24,50',group_name='Gift',items=[dict(name='A',amount='-20',category='Shopping'),dict(name='B',amount='-4,50',category='Freizeit',group_name='')])
        shortcut_api.ingest({**self.body,'ai':ai},self.db)
        with app.connect(self.db) as con:
            self.assertEqual(con.execute('SELECT amount FROM transactions').fetchone()[0],-2450)
            self.assertEqual([tuple(r) for r in con.execute('SELECT amount,group_name FROM items ORDER BY id')],[(-2000,None),(-450,'')])
        self.assertEqual(self.count(),1)

    def test_concurrent_identical_calls_and_deleted_retry(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:shortcut_api.ingest(self.body,self.db),range(2)))
        self.assertEqual(sorted(status for _,status in results),[200,201])
        self.assertEqual(self.count(),1)
        with app.connect(self.db) as con:
            con.execute('DELETE FROM transactions')
        with self.assertRaises(shortcut_api.DeletedImport):
            shortcut_api.ingest(self.body,self.db)
        self.assertEqual(self.count(),0)

    def test_backup_restore_keeps_originals_and_deleted_retry_tombstones(self):
        shortcut_api.ingest(self.body,self.db)
        second={**self.body,'timestamp':'2026-10-19T18:30:00+02:00'}
        deleted,_=shortcut_api.ingest(second,self.db)
        with app.connect(self.db) as con:
            con.execute('DELETE FROM transactions WHERE id=?',(deleted['entry_ids'][0],))
        stream=io.BytesIO();backups.write_archive(self.db,stream,dataset='private')
        backups.restore(io.BytesIO(stream.getvalue()),self.db)
        self.assertEqual(shortcut_api.ingest(self.body,self.db)[1],200)
        with self.assertRaises(shortcut_api.DeletedImport):
            shortcut_api.ingest(second,self.db)
        self.assertEqual(self.count(),1)

    def test_source_write_failure_rolls_back_the_financial_entry(self):
        with app.connect(self.db) as con:
            con.execute("CREATE TRIGGER reject_source BEFORE INSERT ON shortcut_imports BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            shortcut_api.ingest(self.body,self.db)
        self.assertEqual(self.count(),0)

    def test_minimal_fields_use_current_default_category_without_guessing_payment(self):
        app.rename_category('Unkategorisiert','Offen',self.db)
        shortcut_api.ingest({**self.body,'ai':dict(title='Expense',amount='0,01')},self.db)
        with app.connect(self.db) as con:
            self.assertEqual(tuple(con.execute('SELECT amount,category,payment_method FROM transactions').fetchone()),(1,'Offen',''))
