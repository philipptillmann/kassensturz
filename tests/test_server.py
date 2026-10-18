import base64
import io
import os
import shutil
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageFont, ImageDraw

import app as ledger
import receipts
from server import create_app

PASSWORD = 'test-password-for-kassensturz'
ORIGIN = 'http://localhost'


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous = ledger.DB
        ledger.DB = Path(self.tmp.name) / 'expenses.sqlite3'
        self.app = create_app(password=PASSWORD, public_url='')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def tearDown(self):
        ledger.DB = self.previous
        self.tmp.cleanup()

    def login(self, client=None, password=PASSWORD, origin=ORIGIN):
        client = client or self.client
        response = client.post('/api/login', json={'password': password}, headers={'Origin': origin})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.json['csrf']

    def post(self, path, data, csrf, client=None, origin=ORIGIN):
        return (client or self.client).post(path, json=data, headers={'Origin': origin, 'X-CSRF-Token': csrf})

    def test_anonymous_access_and_wrong_password(self):
        self.assertEqual(self.client.get('/').status_code, 302)
        for path in ['/api/data', '/api/export', '/api/session']:
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.get('/healthz').json, {'status': 'ok'})
        with self.client.get('/login') as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post('/api/login', json={'password': 'wrong'}, headers={'Origin': ORIGIN}).status_code, 401)
        self.assertEqual(self.client.get('/api/data').status_code, 401)

    def test_two_devices_share_split_transactions_and_logout_is_independent(self):
        phone = self.app.test_client()
        csrf = self.login()
        phone_csrf = self.login(phone)
        data = {'merchant': 'Amazon', 'date': '2026-10-05', 'amount': '50', 'category': 'Shopping',
                'items': [{'name': 'Fahrradlicht', 'amount': '30', 'category': 'Fahrrad'},
                          {'name': 'Kochtopf', 'amount': '20', 'category': 'Küche & Haushalt'}]}
        self.assertEqual(self.post('/api/transaction', data, csrf).status_code, 200)
        transactions = phone.get('/api/data').json['transactions']
        self.assertEqual(len(transactions), 1)
        self.assertEqual([x['amount'] for x in transactions[0]['items']], [3000, 2000])
        export = phone.get('/api/export')
        self.assertIn('Fahrradlicht', export.get_data(as_text=True))
        cookie = self.client.get_cookie('session').value
        self.assertEqual(self.post('/api/logout', {}, csrf).status_code, 200)
        self.client.set_cookie('session', cookie)
        self.assertEqual(self.client.get('/api/data').status_code, 401)
        self.assertEqual(phone.get('/api/data').status_code, 200)
        self.assertEqual(self.post('/api/category', {'name': 'Werkzeug'}, phone_csrf, phone).status_code, 200)

    def test_csrf_and_login_origin(self):
        self.assertEqual(self.client.post('/api/login', json={'password': PASSWORD}, headers={'Origin': 'https://evil.example'}).status_code, 403)
        csrf = self.login()
        for headers in [{'Origin': ORIGIN}, {'Origin': 'https://evil.example', 'X-CSRF-Token': csrf}, {'X-CSRF-Token': csrf}]:
            self.assertEqual(self.client.post('/api/category', json={'name': 'Bad'}, headers=headers).status_code, 403)
        self.assertNotIn('Bad', self.client.get('/api/data').json['categories'])

    def test_sessions_persist_restart_and_expire(self):
        self.login()
        token = self.client.get_cookie('session').value
        restarted = create_app(password=PASSWORD, public_url='').test_client()
        restarted.set_cookie('session', token)
        self.assertEqual(restarted.get('/api/data').status_code, 200)
        with ledger.connect() as con:
            con.execute('UPDATE sessions SET expires=?', (int(time.time()) - 1,))
        self.assertEqual(restarted.get('/api/data').status_code, 401)

    def test_remembered_session_lasts_ninety_days_and_can_be_revoked(self):
        now = int(time.time())
        with patch('server.time.time', return_value=now):
            response = self.client.post('/api/login', json={'password': PASSWORD, 'remember': True}, headers={'Origin': ORIGIN})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Max-Age=7776000', response.headers['Set-Cookie'])
        token = self.client.get_cookie('session').value
        restarted = create_app(password=PASSWORD, public_url='').test_client()
        restarted.set_cookie('session', token)
        with patch('server.time.time', return_value=now + 8 * 86400):
            self.assertEqual(restarted.get('/api/data').status_code, 200)
        with patch('server.time.time', return_value=now + 90 * 86400):
            self.assertEqual(restarted.get('/api/data').status_code, 401)
        changed = create_app(password=PASSWORD + '-changed', public_url='').test_client()
        changed.set_cookie('session', token)
        self.assertEqual(changed.get('/api/data').status_code, 401)
        self.assertEqual(self.post('/api/logout', {}, response.json['csrf']).status_code, 200)
        restarted.set_cookie('session', token)
        self.assertEqual(restarted.get('/api/data').status_code, 401)
        short = self.client.post('/api/login', json={'password': PASSWORD, 'remember': False}, headers={'Origin': ORIGIN})
        self.assertIn('Max-Age=604800', short.headers['Set-Cookie'])
        invalid = self.client.post('/api/login', json={'password': PASSWORD, 'remember': 'yes'}, headers={'Origin': ORIGIN})
        self.assertEqual(invalid.status_code, 400)

    def test_password_rotation_invalidates_sessions(self):
        self.login()
        token = self.client.get_cookie('session').value
        changed = create_app(password=PASSWORD + '-changed', public_url='').test_client()
        changed.set_cookie('session', token)
        self.assertEqual(changed.get('/api/data').status_code, 401)

    def test_tls_cookies_and_public_origin(self):
        client = create_app(password=PASSWORD, public_url='https://money.example').test_client()
        response = client.post('/api/login', json={'password': PASSWORD}, base_url='https://money.example', headers={'Origin': 'https://money.example'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Secure', response.headers['Set-Cookie'])
        self.assertIn('HttpOnly', response.headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', response.headers['Set-Cookie'])
        self.assertIn('Strict-Transport-Security', response.headers)
        self.assertEqual(client.get('/login', base_url='http://evil.example').status_code, 400)
        self.assertEqual(client.get('/healthz').status_code, 200)

    def test_rate_limit(self):
        with patch('server.check_password_hash', return_value=False):
            for _ in range(20):
                response = self.client.post('/api/login', json={'password': 'wrong'}, headers={'Origin': ORIGIN})
                self.assertEqual(response.status_code, 401)
            response = self.client.post('/api/login', json={'password': PASSWORD}, headers={'Origin': ORIGIN})
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.headers['Retry-After'], '60')

    def test_import_persists_and_duplicates_are_skipped(self):
        csrf = self.login()
        data = {'text': 'Datum;Händler;Betrag\n05.10.2026;Cafe;-4,50\n', 'date_column': 'Datum', 'merchant_column': 'Händler', 'amount_column': 'Betrag'}
        preview = self.post('/api/import-check', data, csrf)
        self.assertEqual(preview.status_code, 200)
        self.assertEqual((preview.json['added'], preview.json['skipped']), (1, 0))
        self.assertEqual(self.client.get('/api/data').json['transactions'], [])
        self.assertEqual(self.post('/api/import', data, csrf).json, {'added': 1, 'skipped': 0})
        preview = self.post('/api/import-check', data, csrf)
        self.assertEqual((preview.json['added'], preview.json['skipped']), (0, 1))
        self.assertEqual(self.post('/api/import', data, csrf).json, {'added': 0, 'skipped': 1})
        restarted = create_app(password=PASSWORD, public_url='').test_client()
        self.login(restarted)
        self.assertEqual(restarted.get('/api/data').json['transactions'][0]['amount'], 450)

    def test_volksbank_source_selection_and_undo_api(self):
        from test_volksbank import sample,booking,SOURCE,OTHER
        csrf=self.login();data={'text':sample(booking(),booking(source=OTHER)),'payment_method':'Bar'}
        preview=self.post('/api/import-preview',data,csrf).json
        self.assertEqual(preview['provider'],'volksbank');self.assertEqual(preview['source_accounts'],[SOURCE,OTHER])
        self.assertEqual(self.post('/api/import',data,csrf).status_code,400)
        data['source_account']=SOURCE
        checked=self.post('/api/import-check',data,csrf).json
        self.assertEqual((checked['added'],len(checked['excluded'])),(1,1))
        self.assertEqual(self.post('/api/import',data,csrf).json['added'],1)
        token=self.post('/api/import-undo-preview',{},csrf).json['token']
        self.assertEqual(self.post('/api/import-undo',{'token':token},csrf).json,{'removed':1})

    def test_ing_auto_detection_and_salary_import_with_undo(self):
        from test_ing import sample,payment
        csrf=self.login()
        data={'text':sample([payment(),payment(kind='Gehalt/Rente',amount='2500')]),'payment_method':'Bar'}
        detected=self.post('/api/import-preview',data,csrf)
        self.assertEqual(detected.status_code,200)
        self.assertEqual((detected.json['provider'],detected.json['count']),('ing',2))
        self.assertNotIn('Kunde',detected.json['headers'])
        preview=self.post('/api/import-check',data,csrf)
        self.assertEqual([r['kind'] for r in preview.json['rows']],['expense','income'])
        self.assertEqual(self.post('/api/import',data,csrf).json,{'added':2,'skipped':0})
        self.assertEqual(self.post('/api/import',data,csrf).json,{'added':0,'skipped':2})
        token=self.post('/api/import-undo-preview',{},csrf).json['token']
        self.assertEqual(self.post('/api/import-undo',{'token':token},csrf).json,{'removed':2})

    def test_csv_undo_api_is_dataset_scoped_and_consumed_once(self):
        csrf=self.login()
        data={'text':'Date;Name;Amount\n2026-10-01;Synthetic cafe;-5,00\n','date_column':'Date','merchant_column':'Name','amount_column':'Amount'}
        self.assertEqual(self.post('/api/import',data,csrf).status_code,200)
        batch=self.post('/api/import-undo-preview',{},csrf).json
        self.assertEqual(batch['count'],1)
        self.assertEqual(self.post('/api/import-undo',{'token':batch['token']},'wrong').status_code,403)
        self.assertEqual(self.post('/api/import-undo?dataset=demo',{'token':batch['token']},csrf).status_code,400)
        self.assertEqual(self.post('/api/import-undo',{'token':batch['token']},csrf).json,{'removed':1})
        self.assertEqual(self.post('/api/import-undo',{'token':batch['token']},csrf).status_code,400)
        self.assertEqual(self.client.get('/api/data').json['transactions'],[])

    def test_bad_json_and_oversized_upload(self):
        csrf = self.login()
        self.assertEqual(self.post('/api/transaction', [], csrf).status_code, 400)
        self.assertEqual(self.post('/api/ocr', {'image': 'not base64'}, csrf).status_code, 400)
        response = self.post('/api/ocr', {'image': 'A' * 17_000_000}, csrf)
        self.assertEqual(response.status_code, 413)

    def test_ocr_endpoint_maps_positions(self):
        csrf = self.login()
        with patch('receipts.recognize_text', return_value='Fahrradlicht 30,00\nKochtopf 20,00\nGesamt 50,00'):
            response = self.post('/api/ocr', {'image': 'unused'}, csrf)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([x['category'] for x in response.json['items']], ['Fahrrad', 'Küche & Haushalt'])

    def test_upload_concurrency_returns_retryable_error(self):
        csrf = self.login()
        receipts.OCR_SLOT.acquire()
        try:
            response = self.post('/api/ocr', {'image': base64.b64encode(b'test').decode()}, csrf)
            self.assertEqual(response.status_code, 429)
        finally:
            receipts.OCR_SLOT.release()

    def test_dataset_isolation_and_restart(self):
        csrf = self.login()
        def post(action, data, dataset):
            return self.post('/api/' + action + '?dataset=' + dataset, data, csrf)
        demo = self.client.get('/api/data?dataset=demo').json
        self.assertGreater(len(demo['transactions']), 10)
        self.assertTrue(any(t['items'] for t in demo['transactions']))
        self.assertEqual(self.client.get('/api/data').json['transactions'], [])
        self.assertEqual(post('category', {'name': 'Nur privat'}, 'private').status_code, 200)
        self.assertNotIn('Nur privat', self.client.get('/api/data?dataset=demo').json['categories'])
        private_tx = {'merchant': 'Private purchase', 'date': '2026-10-08', 'amount': '10', 'category': 'Nur privat'}
        private_id = post('transaction', private_tx, 'private').json['id']
        demo_id = next(t['id'] for t in demo['transactions'] if t['id'] == private_id)
        self.assertEqual(post('delete', {'id': demo_id}, 'demo').status_code, 200)
        self.assertEqual(self.client.get('/api/data').json['transactions'][0]['merchant'], 'Private purchase')
        csv = {'text': 'Datum;Händler;Betrag\n08.10.2026;Demo import;-4,50\n', 'date_column': 'Datum', 'merchant_column': 'Händler', 'amount_column': 'Betrag'}
        self.assertEqual(post('import', csv, 'demo').json['added'], 1)
        self.assertEqual(len(self.client.get('/api/data').json['transactions']), 1)
        demo_export = self.client.get('/api/export?dataset=demo').get_data(as_text=True)
        self.assertIn('Demo import', demo_export)
        self.assertNotIn('Private purchase', demo_export)
        self.assertNotIn('Demo import', self.client.get('/api/export').get_data(as_text=True))
        private_tx.update(id=private_id, amount='12')
        self.assertEqual(post('transaction', private_tx, 'private').status_code, 200)
        restarted = create_app(password=PASSWORD, public_url='').test_client()
        self.login(restarted)
        self.assertEqual(restarted.get('/api/data').json['transactions'][0]['amount'], 1200)
        after_restart = restarted.get('/api/data?dataset=demo').json['transactions']
        self.assertEqual(len(after_restart), len(demo['transactions']))
        self.assertNotIn(demo_id, [t['id'] for t in after_restart])
        self.assertEqual(self.client.get('/api/data?dataset=../../private').status_code, 400)
        self.assertEqual(post('delete', {'id': private_id}, 'invalid').status_code, 400)
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.get('/api/data?dataset=demo').status_code, 401)

    def test_existing_private_data_is_preserved(self):
        ledger.save_transaction({'merchant': 'Existing expense', 'date': '2026-10-01', 'amount': '42', 'category': 'Shopping'})
        restarted = create_app(password=PASSWORD, public_url='').test_client()
        self.login(restarted)
        private = restarted.get('/api/data').json['transactions']
        self.assertEqual([(t['merchant'], t['amount']) for t in private], [('Existing expense', 4200)])

    def test_group_names_persist_export_and_are_isolated_by_dataset(self):
        csrf=self.login()
        data={'merchant':'Gift','date':'2026-10-01','amount':'120','category':'Shopping','group_name':'Gift group'}
        purchase=self.post('/api/transaction',data,csrf).json['id']
        data.update(merchant='Cash contribution',amount='-30')
        self.post('/api/transaction',data,csrf)
        private=self.client.get('/api/data').json['transactions']
        self.assertEqual(len(private),2)
        self.assertEqual({t['group_name'] for t in private},{'Gift group'})
        self.assertEqual(sum(t['amount'] for t in private),9000)
        self.assertNotIn('Gift group',{t['group_name'] for t in self.client.get('/api/data?dataset=demo').json['transactions']})
        self.assertIn('Gift group',self.client.get('/api/export').get_data(as_text=True))
        self.assertNotIn('Gift group',self.client.get('/api/export?dataset=demo').get_data(as_text=True))
        restarted=create_app(password=PASSWORD,public_url='').test_client();self.login(restarted)
        self.assertEqual({t['group_name'] for t in restarted.get('/api/data').json['transactions']},{'Gift group'})
        self.post('/api/delete',{'id':purchase},csrf)
        remaining=self.client.get('/api/data').json['transactions']
        self.assertEqual([(t['merchant'],t['amount']) for t in remaining],[('Cash contribution',-3000)])

    def test_item_groups_survive_restart_and_export_effective_names(self):
        csrf=self.login()
        data={'merchant':'Mixed receipt','date':'2026-10-01','amount':'150','category':'Shopping','group_name':'Receipt group','items':[
            {'name':'Gift','amount':'90','category':'Shopping','group_name':'Gift group'},
            {'name':'Bike light','amount':'35','category':'Fahrrad','group_name':''},
            {'name':'Kitchen','amount':'25','category':'Küche & Haushalt','group_name':None}]}
        self.assertEqual(self.post('/api/transaction',data,csrf).status_code,200)
        restarted=create_app(password=PASSWORD,public_url='').test_client();self.login(restarted)
        tx=restarted.get('/api/data').json['transactions'][0]
        self.assertEqual(tx['amount'],15000)
        self.assertEqual([item['group_name'] for item in tx['items']],['Gift group','',None])
        import csv
        rows=list(csv.reader(io.StringIO(restarted.get('/api/export').get_data(as_text=True)),delimiter=';'))
        self.assertEqual([row[rows[0].index('Gruppe')] for row in rows[1:]],['Gift group','','Receipt group'])
        self.assertEqual(self.client.get('/api/data?dataset=demo').status_code,200)

    def test_category_rename_and_payments_are_dataset_scoped(self):
        csrf=self.login()
        self.assertEqual(self.post('/api/payment-method',{'name':'ING'},csrf).status_code,200)
        data={'merchant':'Purchase','date':'2026-10-01','amount':'10','category':'Fahrrad','payment_method':'ING','items':[{'name':'Light','amount':'10','category':'Fahrrad'}]}
        self.assertEqual(self.post('/api/transaction',data,csrf).status_code,200)
        self.assertEqual(self.post('/api/category-rename',{'old_name':'Fahrrad','name':'Rad'},csrf).status_code,200)
        private=self.client.get('/api/data').json
        self.assertEqual(private['transactions'][0]['category'],'Rad')
        self.assertEqual(private['transactions'][0]['items'][0]['category'],'Rad')
        self.assertEqual(private['transactions'][0]['payment_method'],'ING')
        demo=self.client.get('/api/data?dataset=demo').json
        self.assertIn('Fahrrad',demo['categories']);self.assertNotIn('Rad',demo['categories']);self.assertNotIn('ING',demo['payment_methods'])
        with patch('receipts.recognize_text',return_value='Fahrradlicht 10,00'):
            self.assertEqual(self.post('/api/ocr',{'image':'unused'},csrf).json['items'][0]['category'],'Rad')
        restarted=create_app(password=PASSWORD,public_url='').test_client();self.login(restarted)
        self.assertNotIn('Fahrrad',restarted.get('/api/data').json['categories'])
        export=self.client.get('/api/export').get_data(as_text=True)
        self.assertIn('Zahlungsmittel',export);self.assertIn('ING',export);self.assertIn('Rad',export)
        self.assertEqual(self.post('/api/category-rename',{'old_name':'Rad','name':'Shopping'},csrf).status_code,400)
        self.assertEqual(self.post('/api/payment-method',{'name':''},csrf).status_code,400)

    def test_income_persists_and_is_exported_without_changing_refunds(self):
        csrf=self.login()
        salary={'merchant':'Employer','date':'2026-10-01','amount':'2800','kind':'income','category':'Gehalt','payment_method':'Bar'}
        self.assertEqual(self.post('/api/transaction',salary,csrf).status_code,200)
        self.post('/api/transaction',{'merchant':'Refund','date':'2026-10-02','amount':'-20','category':'Shopping'},csrf)
        restarted=create_app(password=PASSWORD,public_url='').test_client();self.login(restarted)
        data=restarted.get('/api/data').json['transactions']
        self.assertEqual([(t['kind'],t['amount']) for t in data],[('expense',-2000),('income',-280000)])
        self.assertIn('Buchungstyp',restarted.get('/api/export').get_data(as_text=True))
        self.assertIn('Einnahme',restarted.get('/api/export').get_data(as_text=True))

    def test_notes_persist_export_and_stay_in_their_dataset(self):
        csrf=self.login()
        notes='=SUM(1;2)\nPersönliche Notiz <script>nur Text</script>'
        data={'merchant':'Test','date':'2026-10-01','amount':'10','category':'Shopping','notes':notes}
        self.assertEqual(self.post('/api/transaction',data,csrf).status_code,200)
        restarted=create_app(password=PASSWORD,public_url='').test_client();self.login(restarted)
        self.assertEqual(restarted.get('/api/data').json['transactions'][0]['notes'],notes)
        import csv
        rows=list(csv.reader(io.StringIO(restarted.get('/api/export').get_data(as_text=True)),delimiter=';'))
        self.assertEqual(rows[1][rows[0].index('Notizen')],"'"+notes)
        self.assertNotIn(notes,[tx['notes'] for tx in self.client.get('/api/data?dataset=demo').json['transactions']])

    def test_receipt_archive_is_authenticated_atomic_and_dataset_scoped(self):
        csrf=self.login();image=Image.new('RGB',(300,500),'white');stream=io.BytesIO();image.save(stream,format='PNG')
        encoded=base64.b64encode(stream.getvalue()).decode()
        data={'merchant':'Receipt purchase','date':'2026-10-01','amount':'7.25','category':'Shopping','receipt_image':encoded}
        response=self.post('/api/transaction',data,csrf);self.assertEqual(response.status_code,200);txid=response.json['id']
        self.assertTrue(self.client.get('/api/data').json['transactions'][0]['has_receipt'])
        url=f'/api/receipt/{txid}'
        stored=self.client.get(url);self.assertEqual(stored.status_code,200);self.assertEqual(stored.content_type,'image/jpeg')
        self.assertEqual(self.app.test_client().get(url).status_code,401)
        self.assertEqual(self.client.get(url+'?dataset=demo').status_code,404)
        restarted=create_app(password=PASSWORD,public_url='').test_client();self.login(restarted)
        self.assertEqual(restarted.get(url).data,stored.data)
        with ledger.connect() as con:
            backup=sqlite3.connect(':memory:');con.backup(backup)
            self.assertEqual(bytes(backup.execute('SELECT image FROM receipt_images').fetchone()[0]),stored.data);backup.close()
        data.update(id=txid);del data['receipt_image'];data['amount']='8'
        self.assertEqual(self.post('/api/transaction',data,csrf).status_code,200)
        self.assertEqual(self.client.get(url).data,stored.data)
        data.update(receipt_image='invalid',amount='99')
        self.assertEqual(self.post('/api/transaction',data,csrf).status_code,400)
        self.assertEqual(self.client.get('/api/data').json['transactions'][0]['amount'],800)
        del data['receipt_image'];data['remove_receipt']=True
        self.assertEqual(self.post('/api/transaction',data,csrf).status_code,200)
        self.assertEqual(self.client.get(url).status_code,404)
        data['remove_receipt']=False;data['receipt_image']=encoded
        self.post('/api/transaction',data,csrf)
        self.assertEqual(self.post('/api/delete',{'id':txid},csrf).status_code,200)
        with ledger.connect() as con:self.assertEqual(con.execute('SELECT count(*) FROM receipt_images').fetchone()[0],0)

    def test_own_accounts_and_transfers_are_persistent_and_dataset_scoped(self):
        csrf=self.login()
        for name,share in [('Own',100),('Shared',50)]:
            self.assertEqual(self.post('/api/account',{'name':name,'share_percent':share,'share_income':True},csrf).status_code,200)
        base={'date':'2026-10-01','category':'Shopping','merchant':'Umbuchung'}
        outgoing=self.post('/api/transaction',dict(base,amount='200',payment_method='Own'),csrf).json['id']
        self.assertFalse(self.client.get('/api/data').json['transactions'][0]['internal_transfer'])
        incoming=self.post('/api/transaction',dict(base,amount='-200',payment_method='Shared'),csrf).json['id']
        data=self.client.get('/api/data').json
        self.assertEqual(len(data['transfer_links']),1)
        self.assertTrue(all(tx['internal_transfer'] for tx in data['transactions']))
        self.assertEqual(next(a['share_bp'] for a in data['accounts'] if a['payment_method']=='Shared'),5000)
        self.assertNotIn('Own',[a['payment_method'] for a in self.client.get('/api/data?dataset=demo').json['accounts']])
        self.assertEqual(self.post('/api/transfer-reject',{'outgoing_id':outgoing,'incoming_id':incoming},csrf).status_code,200)
        restarted=create_app(password=PASSWORD,public_url='').test_client();self.login(restarted)
        self.assertFalse(any(tx['internal_transfer'] for tx in restarted.get('/api/data').json['transactions']))

    def test_home_screen_assets_are_available_before_login(self):
        manifest = self.client.get('/manifest.webmanifest')
        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(manifest.json['name'], 'Kassensturz')
        self.assertEqual(manifest.json['start_url'], '/')
        manifest.close()
        for size in (180, 192, 512):
            response = self.client.get(f'/icons/icon-{size}.png')
            self.assertEqual(response.status_code, 200)
            with Image.open(io.BytesIO(response.data)) as icon:
                self.assertEqual(icon.size, (size, size))
            response.close()
        with self.client.get('/icons/icon.svg') as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/api/data').status_code, 401)


class ReceiptTests(unittest.TestCase):
    def test_archive_jpeg_limits_size_preserves_orientation_and_strips_metadata(self):
        image=Image.new('RGB',(3600,1800),'white')
        exif=Image.Exif();exif[274]=6;exif[270]='Private camera metadata'
        stream=io.BytesIO();image.save(stream,format='JPEG',exif=exif)
        result=receipts.prepare_jpeg(base64.b64encode(stream.getvalue()).decode())
        with Image.open(io.BytesIO(result)) as decoded:
            self.assertEqual(decoded.format,'JPEG');self.assertEqual(decoded.size,(1600,3200))
            self.assertFalse(decoded.getexif());self.assertEqual(decoded.mode,'RGB')
    def test_archive_heic_and_transparency_and_small_images(self):
        from pillow_heif import from_pillow
        for format in ('HEIC','PNG'):
            image=Image.new('RGBA',(100,60),(0,0,0,0));stream=io.BytesIO()
            if format=='HEIC':from_pillow(image.convert('RGB')).save(stream)
            else:image.save(stream,format='PNG')
            result=receipts.prepare_jpeg(base64.b64encode(stream.getvalue()).decode())
            with Image.open(io.BytesIO(result)) as decoded:
                self.assertEqual(decoded.format,'JPEG');self.assertEqual(decoded.size,(100,60))
                if format=='PNG':self.assertEqual(decoded.getpixel((0,0)),(255,255,255))
        with self.assertRaises(ValueError):receipts.prepare_jpeg('bad base64')
    def test_real_tesseract_receipt(self):
        if not shutil.which('tesseract'):
            if os.environ.get('CHECK_CONTAINER'):
                self.fail('Container must include Tesseract')
            self.skipTest('Tesseract is not installed on this host; exercised in Docker CI')
        image = Image.new('RGB', (1100, 260), 'white')
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=48)
        draw.text((35, 25), 'Fahrradlicht 30,00', font=font, fill='black')
        draw.text((35, 100), 'Kochtopf 20,00', font=font, fill='black')
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        result = ledger.recognize({'image': base64.b64encode(stream.getvalue()).decode()})
        self.assertIn('Fahrradlicht', result['text'])
        self.assertEqual([x['amount'] for x in result['items']], [30, 20])
        self.assertEqual([x['category'] for x in result['items']], ['Fahrrad', 'Küche & Haushalt'])

    def test_heic_decoding(self):
        from pillow_heif import from_pillow
        image = Image.new('RGB', (100, 60), 'white')
        stream = io.BytesIO()
        from_pillow(image).save(stream)
        paths = []
        def process(args, **kwargs):
            path = Path(args[1])
            paths.append(path)
            with Image.open(path) as decoded:
                self.assertEqual(decoded.size, (100, 60))
            return type('Result', (), {'returncode': 0, 'stdout': 'Kochtopf 20,00'})()
        with patch('receipts.subprocess.run', side_effect=process):
            self.assertEqual(receipts.recognize_text(base64.b64encode(stream.getvalue()).decode()), 'Kochtopf 20,00')
        self.assertFalse(paths[0].exists(), 'Receipt image must be removed after OCR')

    def test_timeout_cleans_up_and_releases_slot(self):
        import subprocess
        image = Image.new('RGB', (40, 40), 'white')
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        with patch('receipts.subprocess.run', side_effect=subprocess.TimeoutExpired('tesseract', 60)):
            with self.assertRaisesRegex(ValueError, 'lange'):
                receipts.recognize_text(base64.b64encode(stream.getvalue()).decode())
        self.assertTrue(receipts.OCR_SLOT.acquire(False))
        receipts.OCR_SLOT.release()

    def test_container_is_nonroot(self):
        if not os.environ.get('CHECK_CONTAINER'):
            self.skipTest('Container-only check')
        self.assertNotEqual(os.getuid(), 0)


if __name__ == '__main__':
    unittest.main()
