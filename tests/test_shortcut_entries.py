import concurrent.futures
import io
import json
from pathlib import Path
import tempfile
import unittest

import app
import backups
import shortcut_api

class ShortcutEntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'ledger.db';app.init(self.db)
        self.body=dict(date='2026-10-19',merchant='Fictional shop',amount='12.50')
    def tearDown(self):self.tmp.cleanup()
    def rows(self):
        with app.connect(self.db) as c:return list(c.execute('SELECT * FROM transactions ORDER BY id'))
    def test_minimal_direct_entry_and_retry_after_edits(self):
        first,status=shortcut_api.ingest(self.body,self.db);self.assertEqual(status,201)
        self.assertEqual((self.rows()[0]['date'],self.rows()[0]['merchant'],self.rows()[0]['amount']),('2026-10-19','Fictional shop',1250))
        with app.connect(self.db) as c:c.execute("UPDATE transactions SET merchant='Edited',amount=2000")
        retry,status=shortcut_api.ingest(dict(reversed(list(self.body.items()))),self.db)
        self.assertEqual(status,200);self.assertEqual(retry['entry_ids'],first['entry_ids'])
        self.assertEqual(len(self.rows()),1);self.assertEqual(self.rows()[0]['merchant'],'Edited')
        with app.connect(self.db) as c:self.assertEqual(json.loads(c.execute('SELECT payload FROM shortcut_imports').fetchone()[0]),self.body)
    def test_income_splits_use_form_sign_convention_and_refunds_stay_expenses(self):
        income=dict(date='2026-10-19',merchant='Salary',amount='100',kind='income',category='Gehalt',payment_method='Bar',notes='x'*4000,items=[dict(name='A',amount='60'),dict(name='B',amount='40')])
        shortcut_api.ingest(income,self.db)
        shortcut_api.ingest({**self.body,'amount':'-12.50'},self.db)
        self.assertEqual([(r['amount'],r['kind']) for r in self.rows()],[(-10000,'income'),(-1250,'expense')])
        with app.connect(self.db) as c:self.assertEqual([r[0] for r in c.execute('SELECT amount FROM items ORDER BY id')],[-6000,-4000])
    def test_uuid_allows_identical_real_entries_and_rejects_changed_data(self):
        one={**self.body,'request_id':'11111111-1111-4111-8111-111111111111'}
        two={**self.body,'request_id':'22222222-2222-4222-8222-222222222222'}
        self.assertEqual(shortcut_api.ingest(one,self.db)[1],201)
        self.assertEqual(shortcut_api.ingest(two,self.db)[1],201)
        self.assertEqual(shortcut_api.ingest(one,self.db)[1],200)
        with self.assertRaises(shortcut_api.ImportConflict):shortcut_api.ingest({**one,'amount':'99'},self.db)
        self.assertEqual(len(self.rows()),2)
    def test_concurrent_uuid_retries_and_backup_deleted_tombstone(self):
        body={**self.body,'request_id':'11111111-1111-4111-8111-111111111111'}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(x[1] for x in pool.map(lambda _:shortcut_api.ingest(body,self.db),range(2))),[200,201])
        with app.connect(self.db) as c:c.execute('DELETE FROM transactions')
        output=io.BytesIO();backups.write_archive(self.db,output,dataset='private')
        backups.restore(io.BytesIO(output.getvalue()),self.db)
        with self.assertRaises(shortcut_api.DeletedImport):shortcut_api.ingest(body,self.db)
        self.assertEqual(len(self.rows()),0)
    def test_uuid_with_missing_source_history_does_not_claim_changed_source(self):
        body={**self.body,'request_id':'11111111-1111-4111-8111-111111111111'}
        shortcut_api.ingest(body,self.db)
        with app.connect(self.db) as c:c.execute('DELETE FROM shortcut_imports')
        for payload in (body,{**body,'amount':'50'}):
            with self.assertRaises(shortcut_api.ImportConflict):shortcut_api.ingest(payload,self.db)
        self.assertEqual(len(self.rows()),1)
        with app.connect(self.db) as c:self.assertEqual(c.execute('SELECT count(*) FROM shortcut_imports').fetchone()[0],0)

    def test_direct_invalid_fields_are_atomic(self):
        changes=[{'date':'19.10.2026'},{'date':'2026-02-30'},{'merchant':''},{'amount':True},{'amount':0},{'amount':'0.001'},{'currency':'USD'},{'kind':'unknown'},{'category':'Missing'},{'payment_method':'Missing'},{'notes':'x'*4001},{'id':1},{'user_id':1},{'dataset':'demo'},{'ai':{}},{'original_message':'test'},{'request_id':'not-a-uuid'},{'items':[dict(name='Part',amount='1')]}]
        for change in changes:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):shortcut_api.ingest({**self.body,**change},self.db)
                self.assertEqual(len(self.rows()),0)
        for name in ('date','merchant','amount'):
            with self.assertRaises(ValueError):shortcut_api.ingest({k:v for k,v in self.body.items() if k!=name},self.db)
    def test_defaults_aliases_and_split_groups(self):
        app.rename_category('Unkategorisiert','Offen',self.db)
        body={**self.body,'group_name':'Gift','items':[dict(name='Part',amount='12.50',group_name='')]}
        shortcut_api.ingest(body,self.db)
        self.assertEqual((self.rows()[0]['category'],self.rows()[0]['payment_method']),('Offen',''))
        with app.connect(self.db) as c:self.assertEqual(c.execute('SELECT group_name FROM items').fetchone()[0],'')
