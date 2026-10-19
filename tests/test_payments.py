import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import app
import accounts
import backups

class PaymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'ledger.db';app.init(self.db)
    def tearDown(self):self.tmp.cleanup()
    def details(self):return {r['name']:r['kind'] for r in accounts.payment_details(self.db)}
    def test_defaults_existing_accounts_and_one_payment_identity(self):
        accounts.configure_account(dict(name='Shared',share_percent='50'),self.db)
        app.init(self.db)
        self.assertEqual(self.details(),{'Bar':'cash','PayPal':'other','Shared':'bank'})
        accounts.configure_payment(dict(name='Shared',kind='bank',share_percent='25'),self.db)
        with app.connect(self.db) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM payment_methods WHERE name='Shared'").fetchone()[0],1)
            self.assertEqual(c.execute("SELECT share_bp FROM account_settings WHERE payment_method='Shared'").fetchone()[0],2500)
    def test_types_persist_and_roundtrip_and_old_backup_defaults(self):
        accounts.configure_payment(dict(name='Coins',kind='cash'),self.db)
        accounts.configure_payment(dict(name='Bar',kind='other'),self.db)
        accounts.configure_payment(dict(name='Bank',kind='bank',share_percent='50'),self.db)
        out=io.BytesIO();backups.write_archive(self.db,out,dataset='private')
        backups.restore(io.BytesIO(out.getvalue()),self.db)
        self.assertEqual((self.details()['Coins'],self.details()['Bar'],self.details()['Bank']),('cash','other','bank'))
        old=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(out.getvalue())) as z,zipfile.ZipFile(old,'w') as target:
            for name in z.namelist():
                data=z.read(name)
                if name=='data.json':
                    meta=json.loads(data);meta.pop('payment_types');data=json.dumps(meta)
                target.writestr(name,data)
        backups.restore(io.BytesIO(old.getvalue()),self.db)
        self.assertEqual((self.details()['Bar'],self.details()['Coins'],self.details()['Bank']),('cash','other','bank'))
    def test_bank_conversion_keeps_entries_and_clears_bank_settings_and_pairings(self):
        for name in ('A','B'):accounts.configure_payment(dict(name=name,kind='bank',share_percent='50'),self.db)
        ids=[app.save_transaction(dict(date='2026-10-19',merchant='Transfer',amount=amount,category='Shopping',payment_method=name),self.db)['id'] for name,amount in [('A','10'),('B','-10')]]
        with app.connect(self.db) as c:c.execute('INSERT INTO transfer_links VALUES (?,?,1)',ids)
        accounts.configure_payment(dict(name='A',kind='cash'),self.db)
        self.assertEqual(self.details()['A'],'cash')
        with app.connect(self.db) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM transactions').fetchone()[0],2)
            self.assertEqual(c.execute('SELECT count(*) FROM transfer_links').fetchone()[0],0)
            self.assertIsNone(c.execute("SELECT * FROM account_settings WHERE payment_method='A'").fetchone())
        accounts.configure_payment(dict(name='A',kind='bank'),self.db)
        self.assertEqual(self.details()['A'],'bank')
        with app.connect(self.db) as c:self.assertIsNone(c.execute("SELECT * FROM payment_types WHERE name='A'").fetchone())
    def test_invalid_config_is_atomic_and_datasets_separate(self):
        accounts.configure_payment(dict(name='Coins',kind='cash'),self.db)
        for data in [dict(name='Coins',kind='bank',iban='bad'),dict(name='Coins',kind='bank',share_percent='101'),dict(name='Coins',kind='invalid')]:
            with self.assertRaises(ValueError):accounts.configure_payment(data,self.db)
            self.assertEqual(self.details()['Coins'],'cash')
        other=Path(self.tmp.name)/'demo.db';app.init(other)
        self.assertNotIn('Coins',{r['name'] for r in accounts.payment_details(other)})
