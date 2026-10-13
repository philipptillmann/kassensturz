import unittest, tempfile
from pathlib import Path
import app

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.previous=app.DB; app.DB=Path(self.tmp.name)/'test.sqlite3'; app.init()
    def tearDown(self):
        app.DB=self.previous; self.tmp.cleanup()
    def transaction(self):
        return {'date':'2026-09-29','merchant':'Amazon','amount':'50,00','category':'Shopping','items':[{'name':'Fahrradlicht','amount':'30','category':'Fahrrad'},{'name':'Topf','amount':'20','category':'Küche & Haushalt'}]}
    def test_split_and_atomic_rejection(self):
        d=self.transaction(); tx=app.save_transaction(d); d['id']=tx['id'];d['items'][0]['amount']='31'
        with self.assertRaises(ValueError): app.save_transaction(d)
        with app.connect() as c:
            self.assertEqual(c.execute('SELECT SUM(amount) FROM items').fetchone()[0],5000)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],1)
    def test_reimport_keeps_identical_real_transactions(self):
        d={'text':'Datum;Händler;Betrag\n29.09.2026;Cafe;-4,50\n29.09.2026;Cafe;-4,50\n','date_column':'Datum','merchant_column':'Händler','amount_column':'Betrag'}
        self.assertEqual(app.import_csv(d),{'added':2,'skipped':0}); self.assertEqual(app.import_csv(d),{'added':0,'skipped':2})
        with app.connect() as c: self.assertEqual(c.execute('SELECT SUM(amount) FROM transactions').fetchone()[0],900)
    def test_invalid_import_is_atomic(self):
        d={'text':'Datum;Händler;Betrag\n29.09.2026;Cafe;-4,50\ninvalid;Cafe;-4,50\n','date_column':'Datum','merchant_column':'Händler','amount_column':'Betrag'}
        with self.assertRaises(ValueError): app.import_csv(d)
        with app.connect() as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],0)
    def test_money(self):
        self.assertEqual(app.cents('1.234,56'),123456)
        self.assertEqual(app.cents('-12.34'),-1234)
        for value in ['NaN','Infinity','1.234','abc']:
            with self.assertRaises(ValueError): app.cents(value)
    def test_category_suggestions(self):
        self.assertEqual(app.suggest_category('LED Fahrradlicht'), 'Fahrrad')
        self.assertEqual(app.suggest_category('Kochtopf Edelstahl'), 'Küche & Haushalt')
        self.assertEqual(app.suggest_category('Artikel 123'), 'Unkategorisiert')
    def test_invalid_category_rolls_back(self):
        d=self.transaction(); d['items'][0]['category']='missing'
        with self.assertRaises(Exception): app.save_transaction(d)
        with app.connect() as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],0)
    def test_groups_preserve_individual_transactions_and_can_be_removed(self):
        d=self.transaction();d['group_name']='  Geschenk  '
        tx=app.save_transaction(d);d['id']=tx['id']
        with app.connect() as c:
            self.assertEqual(c.execute('SELECT group_name FROM transactions').fetchone()[0],'Geschenk')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM items').fetchone()[0],2)
        del d['group_name'];app.save_transaction(d)
        with app.connect() as c:self.assertEqual(c.execute('SELECT group_name FROM transactions').fetchone()[0],'Geschenk')
        d['group_name']='x'*81
        with self.assertRaises(ValueError):app.save_transaction(d)
        d['group_name']='';app.save_transaction(d)
        with app.connect() as c:
            row=c.execute('SELECT * FROM transactions').fetchone()
            self.assertEqual(row['group_name'],'');self.assertEqual(row['amount'],5000)
    def test_group_migration_keeps_existing_data(self):
        import sqlite3
        old=Path(self.tmp.name)/'old.sqlite3'
        with sqlite3.connect(old) as con:
            con.executescript("CREATE TABLE categories(name TEXT PRIMARY KEY); INSERT INTO categories VALUES ('Shopping'); CREATE TABLE transactions(id INTEGER PRIMARY KEY,date TEXT NOT NULL,merchant TEXT NOT NULL,amount INTEGER NOT NULL,category TEXT NOT NULL REFERENCES categories(name),import_key TEXT UNIQUE); INSERT INTO transactions VALUES (1,'2026-10-01','Existing expense',12000,'Shopping','keep-import-key');")
        app.init(old);app.init(old)
        with app.connect(old) as con:
            row=con.execute('SELECT * FROM transactions').fetchone()
            self.assertEqual((row['amount'],row['import_key'],row['group_name']),(12000,'keep-import-key',''))
    def test_item_groups_save_inherit_and_validate_atomically(self):
        d=self.transaction();d['group_name']='Whole receipt'
        d['items'][0]['group_name']='  Gift  ';d['items'][1]['group_name']=''
        tx=app.save_transaction(d);d['id']=tx['id']
        with app.connect() as con:
            self.assertEqual([row[0] for row in con.execute('SELECT group_name FROM items ORDER BY id')],['Gift',''])
            self.assertEqual(con.execute('SELECT amount FROM transactions').fetchone()[0],5000)
        d['items'][1]['group_name']='x'*81
        with self.assertRaises(ValueError):app.save_transaction(d)
        with app.connect() as con:self.assertEqual([row[0] for row in con.execute('SELECT group_name FROM items ORDER BY id')],['Gift',''])
        d['items'][1]['group_name']=None;app.save_transaction(d)
        with app.connect() as con:self.assertEqual([row[0] for row in con.execute('SELECT group_name FROM items ORDER BY id')],['Gift',None])
    def test_category_rename_updates_positions_and_survives_init(self):
        d=self.transaction();app.save_transaction(d)
        app.rename_category('Shopping','Einkäufe');app.rename_category('Fahrrad','Rad');app.rename_category('Unkategorisiert','Offen')
        app.init()
        with app.connect() as con:
            self.assertEqual(con.execute('SELECT category FROM transactions').fetchone()[0],'Einkäufe')
            self.assertEqual(con.execute('SELECT category FROM items ORDER BY id').fetchone()[0],'Rad')
            names={row[0] for row in con.execute('SELECT name FROM categories')}
            self.assertNotIn('Shopping',names);self.assertNotIn('Fahrrad',names);self.assertNotIn('Unkategorisiert',names)
        with self.assertRaises(ValueError):app.rename_category('Rad','Lebensmittel')
        with self.assertRaises(ValueError):app.rename_category('missing','New')
        csv={'text':'Datum;Händler;Betrag\n01.10.2026;Test;-10,00\n','date_column':'Datum','merchant_column':'Händler','amount_column':'Betrag','payment_method':'Bar'}
        app.import_csv(csv)
        with app.connect() as con:self.assertEqual(tuple(con.execute("SELECT category,payment_method FROM transactions WHERE merchant='Test'").fetchone()),('Offen','Bar'))
    def test_payment_validation_and_legacy_edit_preserve_selection(self):
        d=self.transaction();d['payment_method']='PayPal';d['id']=app.save_transaction(d)['id']
        del d['payment_method'];app.save_transaction(d)
        with app.connect() as con:self.assertEqual(con.execute('SELECT payment_method FROM transactions').fetchone()[0],'PayPal')
        d['payment_method']='Unknown'
        with self.assertRaises(ValueError):app.save_transaction(d)
        d['payment_method']='';app.save_transaction(d)
        with app.connect() as con:self.assertEqual(con.execute('SELECT payment_method FROM transactions').fetchone()[0],'')
if __name__=='__main__':unittest.main()
