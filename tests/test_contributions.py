import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import app
import backups
import shortcut_api

class ContributionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'ledger.db';app.init(self.db)
    def tearDown(self):self.tmp.cleanup()
    def entry(self,**changes):return dict(date='2026-11-06',merchant='Friend share',amount='-35',expected_contribution='30',category='Shopping',group_name='Present',notes='Paid via PayPal',**changes)
    def save(self,**changes):
        data=self.entry();data.update(changes);return app.save_transaction(data,self.db)['id']
    def row(self,id):
        with app.connect(self.db) as c:return dict(c.execute('SELECT * FROM transactions WHERE id=?',(id,)).fetchone())
    def test_actual_payment_retained_and_expected_share_does_not_replace_notes(self):
        id=self.save();r=self.row(id)
        self.assertEqual((r['amount'],r['expected_contribution'],r['notes']),(-3500,3000,'Paid via PayPal'))
        data=self.entry();data.pop('expected_contribution');data.pop('notes');data.update(id=id,amount='-40')
        app.save_transaction(data,self.db);r=self.row(id)
        self.assertEqual((r['amount'],r['expected_contribution'],r['notes']),(-4000,3000,'Paid via PayPal'))
        app.init(self.db);self.assertEqual(self.row(id)['expected_contribution'],3000)
        self.save(id=id,expected_contribution=None);self.assertIsNone(self.row(id)['expected_contribution'])
    def test_metadata_validation_is_atomic(self):
        for change in ({'expected_contribution':'-1'},{'expected_contribution':True},{'expected_contribution':'NaN'},{'expected_contribution':'1.001'},{'amount':'35'},{'kind':'income'}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.save(**change)
        with app.connect(self.db) as c:self.assertEqual(c.execute('SELECT count(*) FROM transactions').fetchone()[0],0)
        id=self.save(expected_contribution='0');self.assertEqual(self.row(id)['expected_contribution'],0)
    def test_receipt_and_split_preserved_with_format_three_backup(self):
        id=self.save(items=[dict(name='Gift share',amount='-35',category='Shopping')])
        with app.connect(self.db) as c:c.execute('INSERT INTO receipt_images VALUES (?,?)',(id,b'\xff\xd8synthetic-receipt'))
        out=io.BytesIO();backups.write_archive(self.db,out,dataset='private')
        with zipfile.ZipFile(io.BytesIO(out.getvalue())) as z:
            meta=json.loads(z.read('data.json'));self.assertEqual(meta['version'],3)
        backups.restore(io.BytesIO(out.getvalue()),self.db)
        self.assertEqual((self.row(id)['amount'],self.row(id)['expected_contribution']),(-3500,3000))
        with app.connect(self.db) as c:
            self.assertEqual(c.execute('SELECT image FROM receipt_images').fetchone()[0],b'\xff\xd8synthetic-receipt')
            self.assertEqual(c.execute('SELECT amount FROM items').fetchone()[0],-3500)
    def test_changing_kind_clears_old_expected_metadata_when_not_explicit(self):
        id=self.save();data=self.entry();data.pop('expected_contribution');data.update(id=id,kind='income',amount='35')
        app.save_transaction(data,self.db);self.assertIsNone(self.row(id)['expected_contribution'])
    def test_shortcut_direct_entry_and_retry_accept_optional_agreed_amount(self):
        body=dict(date='2026-11-06',merchant='Friend share',amount='-35',expected_contribution='30')
        first,status=shortcut_api.ingest(body,self.db);self.assertEqual(status,201)
        self.assertEqual(self.row(first['entry_ids'][0])['expected_contribution'],3000)
        self.assertEqual(shortcut_api.ingest(body,self.db)[1],200)
