import csv
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
import app

# Fictional data only. The user's attached export must never be committed.
HEADER=['Bezeichnung Auftragskonto','IBAN Auftragskonto','BIC Auftragskonto','Bankname Auftragskonto','Buchungstag','Valutadatum','Name Zahlungsbeteiligter','IBAN Zahlungsbeteiligter','BIC (SWIFT-Code) Zahlungsbeteiligter','Buchungstext','Verwendungszweck','Betrag','Waehrung','Saldo nach Buchung','Bemerkung','Gekennzeichneter Umsatz','Glaeubiger ID','Mandatsreferenz']
SOURCE='DE00000000000000000000'
OTHER='DE11111111111111111111'

def booking(source=SOURCE,amount='-23,45',name='Fictional shop'):
    return ['Demo account',source,'DEMO','Example bank','03.10.2026','02.10.2026',name,'de 2222','DEMO','Lastschrift','Fictional purpose',amount,'EUR','1.234,56','Fixture note','','Demo creditor','Demo mandate']

def sample(*rows):
    out=io.StringIO();w=csv.writer(out,delimiter=';');w.writerow(HEADER);w.writerows(rows or [booking()]);return out.getvalue()

class VolksbankTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'ledger.db';app.init(self.db)
    def tearDown(self):self.tmp.cleanup()
    def data(self,text,source='',account='Bar'):return dict(text=text,payment_method=account,source_account=source)
    def test_mapping_dates_counterparty_notes_and_credit_kind(self):
        row=booking();row[10]='Quoted; purpose\nsecond line'
        text='\ufeff'+sample(row,booking(amount='10',name='Fictional refund'))
        h,rows=app.read_csv(text);self.assertTrue(app.volksbank_format(h));self.assertEqual(app.volksbank_accounts(rows),[SOURCE])
        app.import_csv(self.data(text),self.db)
        with app.connect(self.db) as c:
            entries=list(c.execute('SELECT * FROM transactions ORDER BY id'))
            self.assertEqual((entries[0]['date'],entries[0]['amount'],entries[0]['counterparty_iban']),('2026-10-03',2345,'DE2222'))
            self.assertEqual(entries[0]['notes'],'Lastschrift\nQuoted; purpose\nsecond line\nFixture note\nDemo creditor\nDemo mandate')
            self.assertEqual((entries[1]['amount'],entries[1]['kind']),(-1000,'expense'))
    def test_multiaccount_requires_selection_and_preserves_scopes(self):
        text=sample(booking(),booking(source=OTHER))
        with self.assertRaises(ValueError):app.import_csv(self.data(text),self.db)
        with self.assertRaises(ValueError):app.import_csv(self.data(text,source='unknown'),self.db)
        p=app.preview_import(self.data(text,source=SOURCE),self.db)
        self.assertEqual((p['added'],len(p['excluded'])),(1,1))
        app.import_csv(self.data(text,source=SOURCE),self.db)
        self.assertEqual(app.preview_import(self.data(text,source=OTHER),self.db)['added'],1)
        self.assertEqual(app.preview_import(self.data(text,source=SOURCE,account='PayPal'),self.db)['added'],1)
    def test_occurrences_balance_and_note_changes_and_reordering(self):
        rows=[booking(),booking(),booking(name='Other shop')]
        app.import_csv(self.data(sample(*rows)),self.db)
        for r in rows:r[13]='0';r[14]='Edited note';r[15]='X'
        text=sample(*reversed(rows))
        self.assertEqual(app.preview_import(self.data(text),self.db)['skipped'],3)
        token=app.last_csv_import(self.db)['token']
        self.assertEqual(app.revert_csv_import(token,self.db)['removed'],3)
        self.assertEqual(app.import_csv(self.data(text),self.db)['added'],3)
    def test_invalid_selected_rows_abort_and_zero_is_reported(self):
        for idx,value in [(12,'USD'),(4,'31.02.2026'),(5,'bad'),(11,'1,234'),(7,'X'*35),(1,'')]:
            bad=booking();bad[idx]=value
            with self.assertRaises(ValueError):app.import_csv(self.data(sample(booking(),bad)),self.db)
        with self.assertRaises(ValueError):app.import_csv(self.data(sample(booking()[:-1])),self.db)
        with app.connect(self.db) as c:self.assertEqual(c.execute('SELECT count(*) FROM transactions').fetchone()[0],0)
        p=app.preview_import(self.data(sample(booking(amount='0'))),self.db)
        self.assertEqual((p['added'],len(p['excluded'])),(0,1))
    def test_shared_native_identity(self):
        result,_=app.volksbank_rows(app.read_csv(sample())[1],'Bar')
        self.assertEqual(result[0][4],'vb:8a2526a0e07d0150840e1b9e960654dce9c4a475a5a418e8e15c8d71c18b7a62')
