import datetime
import json
import tempfile
import unittest
from pathlib import Path

import app as ledger
import accounts


def test_iban(number):
    bban='50010517'+str(number).zfill(10)
    return 'DE'+str(98-int(bban+'131400')%97).zfill(2)+bban


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'expenses.sqlite3';ledger.init(self.db)
        accounts.configure_account({'name':'Own','iban':test_iban(1),'share_percent':'100'},self.db)
        accounts.configure_account({'name':'Shared','iban':test_iban(2),'share_percent':'50'},self.db)
    def tearDown(self):self.tmp.cleanup()
    def tx(self,name,amount,payment,date='2026-10-01',group=''):
        return ledger.save_transaction({'merchant':name,'amount':amount,'date':date,'payment_method':payment,'category':'Shopping','group_name':group},db=self.db)['id']
    def links(self):
        with ledger.connect(self.db) as con:return list(con.execute('SELECT * FROM transfer_links'))
    def test_clear_transfers_match_across_months_and_can_be_rejected(self):
        out=self.tx('Umbuchung','200','Own','2026-09-30');incoming=self.tx('Übertrag','-200','Shared','2026-10-01')
        accounts.reconcile_transfers(self.db);self.assertEqual(len(self.links()),1)
        accounts.reject_transfer({'outgoing_id':out,'incoming_id':incoming},self.db);accounts.reconcile_transfers(self.db);self.assertEqual(len(self.links()),0)
    def test_same_amount_alone_requires_confirmation_and_stale_pair_is_removed(self):
        out=self.tx('A purchase','100','Own');incoming=self.tx('A receipt','-100','Shared')
        accounts.reconcile_transfers(self.db);self.assertEqual(len(self.links()),0)
        accounts.confirm_transfer({'outgoing_id':out,'incoming_id':incoming},self.db);self.assertEqual(len(self.links()),1)
        with ledger.connect(self.db) as con:con.execute('UPDATE transactions SET amount=-90 WHERE id=?',(incoming,))
        accounts.reconcile_transfers(self.db);self.assertEqual(len(self.links()),0)
    def test_ambiguous_matches_and_expense_groups_are_not_auto_hidden(self):
        self.tx('Umbuchung','100','Own');self.tx('Umbuchung','100','Own');self.tx('Umbuchung','-100','Shared')
        accounts.reconcile_transfers(self.db);self.assertEqual(len(self.links()),0)
        with ledger.connect(self.db) as con:con.execute('DELETE FROM transactions')
        self.tx('Umbuchung','100','Own',group='Gift');self.tx('Umbuchung','-100','Shared')
        accounts.reconcile_transfers(self.db);self.assertEqual(len(self.links()),0)
    def test_import_has_bank_scoped_duplicates_and_iban_matching(self):
        def csv(payment,amount,counter):return {'text':f'Datum;Text;Betrag;IBAN\n01.10.2026;Payment;{amount};{counter}\n','date_column':'Datum','merchant_column':'Text','amount_column':'Betrag','counterparty_column':'IBAN','payment_method':payment}
        self.assertEqual(ledger.import_csv(csv('Own','-200',test_iban(2)),self.db)['added'],1)
        self.assertEqual(ledger.import_csv(csv('Shared','200',test_iban(1)),self.db)['added'],1)
        self.assertEqual(ledger.import_csv(csv('Own','-200',test_iban(2)),self.db)['skipped'],1)
        accounts.reconcile_transfers(self.db);self.assertEqual(len(self.links()),1)
        self.assertEqual(ledger.import_csv(csv('Shared','-200',''),self.db)['added'],1)
    def test_account_validation_and_share_persist(self):
        ledger.init(self.db)
        with ledger.connect(self.db) as con:self.assertEqual(con.execute("SELECT share_bp FROM account_settings WHERE payment_method='Shared'").fetchone()[0],5000)
        for value in ('NaN','101','-1','50.001'):
            with self.assertRaises(ValueError):accounts.configure_account({'name':'Shared','share_percent':value},self.db)
        with self.assertRaises(ValueError):accounts.configure_account({'name':'Bad','iban':'DE00123'},self.db)
        with self.assertRaises(ValueError):accounts.configure_account({'name':'Other','iban':test_iban(1)},self.db)
