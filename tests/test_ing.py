import csv
import io
import tempfile
import unittest
from pathlib import Path
import app

HEADER=['Buchung','Wertstellungsdatum','Auftraggeber/Empfänger','Buchungstext','Verwendungszweck','Referenz','Saldo','Währung','Betrag','Währung']

def sample(rows=None, preamble=True):
    rows=rows if rows is not None else [payment()]
    out=io.StringIO();w=csv.writer(out,delimiter=';')
    if preamble:
        w.writerow(['Umsatzanzeige','Synthetic fixture only']+['']*8)
        w.writerow(['IBAN','DE00000000000000000000']+['']*8)
        w.writerow(['Kunde','Example Person']+['']*8)
        w.writerow(['']*10)
    w.writerow(HEADER);w.writerows(rows)
    return out.getvalue()

def payment(name='Example shop',kind='Lastschrift',amount='-10,50',purpose='Example purpose',reference=''):
    return ['30.09.2026','29.09.2026',name,kind,purpose,reference,'9.876,54','EUR',amount,'EUR']

class IngTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'ledger.db';app.init(self.db)
    def tearDown(self):self.tmp.cleanup()
    def data(self,text,account='Bar'):return dict(text=text,payment_method=account)
    def test_preamble_duplicate_currency_booking_date_and_notes(self):
        text=sample([payment(purpose='Quoted; purpose\nsecond line',reference='fixture-ref')])
        columns,rows=app.read_csv('\ufeff'+text)
        self.assertTrue(app.ing_format(columns));self.assertEqual(len(rows),1)
        self.assertNotIn('IBAN',rows[0]);self.assertEqual(rows[0]['Betragswährung'],'EUR')
        app.import_csv(self.data(text),self.db)
        with app.connect(self.db) as c:
            r=c.execute('SELECT * FROM transactions').fetchone()
            self.assertEqual((r['date'],r['amount'],r['merchant']),('2026-09-30',1050,'Example shop'))
            self.assertEqual(r['notes'],'Lastschrift\nQuoted; purpose\nsecond line\nfixture-ref')
    def test_shared_native_identity_fixture(self):
        entries,_=app.ing_rows(app.read_csv(sample())[1],'Bar')
        self.assertEqual(entries[0][4],'ing:5b433d3a38b0b5e0b794b7024ba9da27198b3f53e7419b94412a3982a1cbd172')

    def test_salary_refund_and_zero_preview_then_undo(self):
        text=sample([payment(kind='Gehalt/Rente',amount='1234'),payment(kind='Gutschrift',amount='25'),payment(amount='0')])
        p=app.preview_import(self.data(text),self.db)
        self.assertEqual((p['added'],len(p['excluded'])),(2,1))
        self.assertEqual([r['kind'] for r in p['rows']],['income','expense'])
        app.import_csv(self.data(text),self.db)
        self.assertEqual(app.revert_csv_import(app.last_csv_import(self.db)['token'],self.db),{'removed':2})
        self.assertEqual(app.import_csv(self.data(text),self.db)['added'],2)
    def test_duplicate_occurrences_and_changed_balance_and_order(self):
        rows=[payment(),payment(),payment(name='Other')]
        app.import_csv(self.data(sample(rows)),self.db)
        for row in rows:row[6]='1,00'
        repeat=sample(list(reversed(rows)),preamble=False)
        self.assertEqual(app.preview_import(self.data(repeat),self.db)['skipped'],3)
        self.assertEqual(app.preview_import(self.data(repeat,'PayPal'),self.db)['added'],3)
        rows.append(payment(reference='new reference'))
        self.assertEqual(app.import_csv(self.data(sample(rows)),self.db)['added'],1)
    def test_invalid_currency_width_date_and_amount_abort_whole_import(self):
        for index,value in [(7,'USD'),(9,'USD'),(0,'31.02.2026'),(1,'bad'),(8,'1,234')]:
            row=payment();row[index]=value
            with self.assertRaises(ValueError):app.import_csv(self.data(sample([payment(),row])),self.db)
        with self.assertRaises(ValueError):app.import_csv(self.data(sample([payment(),payment()[:-1]])),self.db)
        with self.assertRaises(ValueError):app.import_csv(self.data(sample(),account=''),self.db)
        with app.connect(self.db) as c:self.assertEqual(c.execute('SELECT count(*) FROM transactions').fetchone()[0],0)
    def test_quoted_comma_generic_csv_still_works(self):
        text='"Date","Name","Amount"\n"2026-10-01","Synthetic shop","-1.00"\n'
        headers,rows=app.read_csv(text)
        self.assertEqual(headers,['Date','Name','Amount']);self.assertEqual(rows[0]['Name'],'Synthetic shop')
