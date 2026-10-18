import csv
import io
import tempfile
import unittest
from pathlib import Path
import app

HEADERS = 'datetime;date;account_type;category;type;asset_class;name;symbol;shares;price;amount;fee;tax;currency;original_amount;original_currency;fx_rate;description;transaction_id;counterparty_name;counterparty_iban;payment_reference;mcc_code'.split(';')

def sample(*overrides):
    out = io.StringIO(); writer = csv.DictWriter(out, HEADERS, delimiter=';'); writer.writeheader()
    for i, override in enumerate(overrides):
        values=dict(datetime='2026-09-30T23:30:00Z', date='2026-10-01', account_type='DEFAULT', category='CASH', type='CARD_TRANSACTION', name='Synthetic shop', amount='-12.34', currency='EUR', transaction_id=f'fixture-{i}')
        values.update(override);writer.writerow(values)
    return out.getvalue()

class TradeRepublicTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'ledger.db';app.init(self.db)
    def tearDown(self): self.tmp.cleanup()
    def data(self, text, **kw): return dict(text=text, payment_method='Bar', **kw)
    def test_dates_signs_and_explicit_exclusions(self):
        text=sample({}, {'category':'TRADING','type':'BUY'}, {'type':'INTEREST_PAYMENT'}, {'type':'TAX_OPTIMIZATION'})
        p=app.preview_import(self.data(text), self.db)
        self.assertEqual((p['added'],len(p['excluded'])),(1,3))
        self.assertEqual((p['rows'][0]['date'],p['rows'][0]['amount']),('2026-10-01',1234))
    def test_ids_preserve_identical_payments_and_survive_reordering_edits(self):
        text=sample({}, {})
        self.assertEqual(app.import_csv(self.data(text),self.db)['added'],2)
        rows=list(csv.DictReader(io.StringIO(text),delimiter=';'));rows.reverse();rows[0]['name']='Edited'
        out=io.StringIO();w=csv.DictWriter(out,HEADERS,delimiter=';');w.writeheader();w.writerows(rows)
        self.assertEqual(app.preview_import(self.data(out.getvalue()),self.db)['skipped'],2)
        self.assertEqual(app.preview_import(dict(text=text,payment_method='PayPal'),self.db)['added'],2)
    def test_invalid_supported_row_is_atomic(self):
        for change in ({'currency':'USD'},{'transaction_id':''},{'date':'bad'},{'amount':'1.234'}):
            with self.assertRaises(ValueError): app.import_csv(self.data(sample({},change)),self.db)
        with app.connect(self.db) as c: self.assertEqual(c.execute('SELECT count(*) FROM transactions').fetchone()[0],0)
