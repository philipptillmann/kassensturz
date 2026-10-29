import gc
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import app as ledger
import backups
import wealth

TODAY = '2026-01-01'


def add(doc, name='Giro', kind='cash', value=100000, rate=0, date=TODAY, maturity=''):
    return wealth.apply(doc, dict(op='asset', name=name, type=kind, value=value, date=date, rate_bp=rate, maturity=maturity), TODAY)


def move(doc, amount=25000, date=TODAY, **extra):
    return wealth.apply(doc, dict(op='event', kind='transfer', amount=amount, date=date, to=2, **{'from': 1}, **extra), date)


class WealthMathTests(unittest.TestCase):
    def setUp(self):
        self.doc = wealth.empty()
        add(self.doc); add(self.doc, 'Tagesgeld', 'savings', 0)

    def test_transfer_conserves_total_and_same_day_snapshot(self):
        move(self.doc)
        self.assertEqual([wealth.cash(self.doc, a, TODAY) for a in self.doc['assets']], [75000,25000])
        add(self.doc, 'Drittes Konto', value=0)
        wealth.apply(self.doc, dict(op='asset', id=2, name='Tagesgeld', type='savings', rate_bp=0, maturity='', value=25000, date=TODAY), TODAY)
        move(self.doc, 5000)
        self.assertEqual([wealth.cash(self.doc, a, TODAY) for a in self.doc['assets']], [70000,30000,0])

    def test_month_end_schedule_and_idempotent_execution(self):
        wealth.apply(self.doc, dict(op='plan', name='Sparen', amount=10000, start='2026-01-31', end='2026-03-31', every=1, enabled=True, to=2, **{'from': 1}), TODAY)
        wealth.apply(self.doc, {'op':'run-plans'}, '2026-03-31')
        self.assertEqual([e['date'] for e in self.doc['events']], ['2026-01-31','2026-02-28','2026-03-31'])
        wealth.apply(self.doc, {'op':'run-plans'}, '2026-03-31')
        self.assertEqual(len(self.doc['events']), 3)
        self.assertEqual(sum(wealth.cash(self.doc,a,'2026-03-31') for a in self.doc['assets']),100000)

    def test_unfunded_plan_does_not_create_forecast_money(self):
        wealth.apply(self.doc, dict(op='plan', name='Zu viel', amount=200000, start='2026-01-02', end='', every=1, enabled=True, to=2, **{'from':1}), TODAY)
        report=wealth.forecast(self.doc, 1, today=TODAY)
        self.assertEqual(report['skipped'],1)
        self.assertEqual(report['points'][-1]['total'],100000)

    def test_paper_gains_cannot_fund_cash_transfers(self):
        doc=wealth.empty();add(doc,'Depot',kind='brokerage',value=0,rate=500);add(doc,'Giro',value=0)
        wealth.apply(doc,dict(op='position',id=1,name='ETF',symbol='',units=10000000,price=10000000,date=TODAY),TODAY)
        wealth.apply(doc,dict(op='plan',name='Auszahlung',amount=1000,start='2026-01-02',end='',every=1,enabled=True,to=2,**{'from':1}),TODAY)
        result=wealth.forecast(doc,1,today=TODAY)
        self.assertEqual(result['skipped'],1)
        self.assertGreater(result['points'][-1]['total'],10000)

    def test_fixed_interest_maturity_and_negative_returns(self):
        for rate, maturity, expected in [(1200,'',1009863),(1200,'2026-01-16',1004932),(-1200,'',990137)]:
            doc=wealth.empty();add(doc,kind='savings' if not maturity else 'fixed',value=1000000,rate=rate,maturity=maturity)
            self.assertEqual(wealth.forecast(doc,1,today=TODAY)['points'][-1]['total'],expected)
        doc=wealth.empty();add(doc,kind='fixed',value=1000000,rate=1200,maturity='2026-01-16')
        self.assertEqual(wealth.forecast(doc,12,today=TODAY)['points'][-1]['total'],1004932)

    def test_trade_conserves_total_and_rejects_oversell(self):
        doc=wealth.empty();add(doc,kind='brokerage')
        wealth.apply(doc,dict(op='trade',id=1,name='ETF',symbol='EXAMPLE',units=3000000,price=10000000,date=TODAY),TODAY)
        self.assertEqual(wealth.cash(doc,doc['assets'][0],TODAY),97000)
        self.assertEqual(wealth.holding(doc['assets'][0]),3000)
        wealth.apply(doc,dict(op='trade',id=1,name='ETF',symbol='EXAMPLE',units=1000000,price=12000000,date=TODAY,sell=True),TODAY)
        self.assertEqual(wealth.cash(doc,doc['assets'][0],TODAY),98200)
        self.assertEqual(wealth.holding(doc['assets'][0]),2400)
        with self.assertRaises(ValueError):
            wealth.apply(doc,dict(op='trade',id=1,name='ETF',symbol='EXAMPLE',units=9000000,price=12000000,date=TODAY,sell=True),TODAY)

    def test_invalid_references_precision_and_duplicate_links(self):
        with self.assertRaises(ValueError): move(self.doc, 100001)
        with self.assertRaises(ValueError): move(self.doc, 1000, entries=[8,8])
        with self.assertRaises(ValueError): wealth.integer(True)
        with self.assertRaises(ValueError): wealth.forecast(self.doc, 361)
        self.assertEqual(wealth.rounded(5,10),1)
        self.assertEqual(wealth.rounded(-5,10),-1)

    def test_optional_quote_parser_and_no_request_on_invalid_symbol(self):
        response=io.BytesIO(json.dumps({'Global Quote':{'01. symbol':'TEST.DE','05. price':'12.345678','07. latest trading day':'2026-01-01'}}).encode())
        with patch('wealth.urlopen', return_value=response) as request:
            self.assertEqual(wealth.fetch_quote('TEST.DE','freeKey'),dict(price=12345678,date=TODAY))
            self.assertIn('GLOBAL_QUOTE', request.call_args.args[0])
            self.assertNotIn('entitlement',request.call_args.args[0])
        with patch('wealth.urlopen') as request:
            with self.assertRaises(ValueError): wealth.fetch_quote('https://evil','key')
            request.assert_not_called()


class WealthPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/'expenses.sqlite3'
        ledger.init(self.db)
        self.today=__import__('datetime').date.today().isoformat()
        for name,kind,value in [('Giro','cash',100000),('Depot','brokerage',0)]:
            wealth.update(self.db,dict(op='asset',name=name,type=kind,value=value,date=self.today,rate_bp=0,maturity=''))

    def tearDown(self):
        gc.collect()
        self.tmp.cleanup()

    def test_failed_batch_rolls_back_and_bank_link_is_separate(self):
        wealth.update(self.db,dict(op='plan',name='Zuerst möglich',amount=10000,start=self.today,end='',every=1,enabled=True,to=2,**{'from':1}))
        wealth.update(self.db,dict(op='plan',name='Sparen',amount=200000,start=self.today,end='',every=1,enabled=True,to=2,**{'from':1}))
        with self.assertRaises(ValueError): wealth.update(self.db,{'op':'run-plans'})
        with ledger.connect(self.db) as con: self.assertEqual(wealth.load(con)['events'],[])
        tx=ledger.save_transaction(dict(date=self.today,merchant='Depotübertrag',amount='250',category='Shopping'),db=self.db)
        wealth.update(self.db,dict(op='event',date=self.today,kind='transfer',amount=25000,to=2,**{'from':1}))
        wealth.update(self.db,dict(op='link',id=1,entries=[tx['id']]))
        with ledger.connect(self.db) as con:
            doc=wealth.load(con)
            self.assertEqual(wealth.linked_entries(doc),{tx['id']})
            self.assertEqual(len(doc['events']),1)
            self.assertEqual(sum(wealth.cash(doc,a,self.today) for a in doc['assets']),100000)
        con.close()

    def test_quote_update_does_not_store_key_and_failure_keeps_value(self):
        wealth.update(self.db,dict(op='position',id=2,name='ETF',symbol='TEST.DE',units=1000000,price=1000000,date=self.today))
        command=dict(id=2,name='ETF',key='privateFreeKey',eur_confirmed=True)
        with patch('wealth.fetch_quote',return_value={'price':2000000,'date':self.today}):
            wealth.quote_update(self.db,command)
        with ledger.connect(self.db) as con: before=con.execute('SELECT data FROM wealth_state').fetchone()[0]
        con.close();self.assertNotIn('privateFreeKey',before)
        with patch('wealth.fetch_quote',side_effect=ValueError('offline')):
            with self.assertRaises(ValueError): wealth.quote_update(self.db,command)
        with ledger.connect(self.db) as con: self.assertEqual(con.execute('SELECT data FROM wealth_state').fetchone()[0],before)
        con.close()

    def test_portable_backup_and_legacy_restore(self):
        stream=io.BytesIO();backups.write_archive(self.db,stream,'private')
        with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as archive:
            meta=json.loads(archive.read('data.json'))
        self.assertEqual(meta['version'],2)
        self.assertEqual(len(meta['wealth']['assets']),2)
        target=Path(self.tmp.name)/'restored.sqlite3';ledger.init(target)
        backups.restore(io.BytesIO(stream.getvalue()),target)
        with ledger.connect(target) as con: self.assertEqual(wealth.load(con),meta['wealth'])
        con.close()
        meta.pop('wealth');meta['version']=1
        legacy=io.BytesIO()
        with zipfile.ZipFile(legacy,'w') as archive: archive.writestr('data.json',json.dumps(meta))
        backups.restore(io.BytesIO(legacy.getvalue()),target)
        with ledger.connect(target) as con: self.assertEqual(wealth.load(con),wealth.empty())
        con.close()

    def test_authenticated_api_dataset_isolation_and_csrf(self):
        from server import create_app
        previous=ledger.DB;ledger.DB=self.db
        try:
            web=create_app(password='local-test-password',public_url='')
            client=web.test_client()
            self.assertEqual(client.post('/api/wealth',json={'op':'run-plans'},headers={'Origin':'http://localhost'}).status_code,401)
            login=client.post('/api/login',json={'password':'local-test-password'},headers={'Origin':'http://localhost'})
            headers={'Origin':'http://localhost','X-CSRF-Token':login.json['csrf']}
            self.assertEqual(client.post('/api/wealth',json={'op':'run-plans'},headers={'Origin':'http://localhost'}).status_code,403)
            self.assertEqual(len(client.get('/api/data').json['wealth']['assets']),2)
            self.assertEqual(client.get('/api/data?dataset=demo').json['wealth']['assets'],[])
            result=client.post('/api/wealth',json=dict(op='event',date=self.today,kind='transfer',amount=10000,to=2,**{'from':1}),headers=headers)
            self.assertEqual(result.status_code,200,result.json)
            self.assertEqual(client.post('/api/wealth-report',json={'months':12},headers=headers).json['total'],100000)
            self.assertEqual(client.get('/api/data').json['transactions'],[])
            tx=ledger.save_transaction(dict(date=self.today,merchant='Anlage',amount='100',category='Shopping'),db=self.db)
            result=client.post('/api/wealth',json=dict(op='link',id=1,entries=[tx['id']]),headers=headers)
            self.assertEqual(result.status_code,200,result.json)
            self.assertTrue(client.get('/api/data').json['transactions'][0]['wealth_transfer'])
            self.assertIn('Vermögensumbuchung',client.get('/api/export').get_data(as_text=True))
            self.assertEqual(client.post('/api/delete',json={'id':tx['id']},headers=headers).status_code,400)
            self.assertEqual(client.post('/api/wealth',json=dict(op='link',id=1,entries=[]),headers=headers).status_code,200)
            self.assertFalse(client.get('/api/data').json['transactions'][0]['wealth_transfer'])
        finally:
            ledger.DB=previous
