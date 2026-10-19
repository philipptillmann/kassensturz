import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import app as ledger
from server import create_app

PASSWORD='test-shortcuts-password'
ORIGIN='http://localhost'


class ShortcutHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=ledger.DB;ledger.DB=Path(self.tmp.name)/'expenses.sqlite3'
        self.web=create_app(password=PASSWORD,public_url='');self.client=self.web.test_client();self.remote=self.web.test_client()
        self.csrf=self.login(self.client)
        self.assertEqual(self.post('users/migrate',dict(username='owner',password=PASSWORD)).status_code,200)
        self.csrf=self.login(self.client,'owner')
        self.body=json.loads((ledger.ROOT/'docs/examples/shortcut-expense.json').read_text())

    def tearDown(self):
        ledger.DB=self.old;self.tmp.cleanup()

    def login(self,client,name=None,password=PASSWORD):
        response=client.post('/api/login',json={'username':name,'password':password},headers={'Origin':ORIGIN})
        self.assertEqual(response.status_code,200,response.json)
        return response.json['csrf']

    def post(self,path,data,client=None,csrf=None):
        return (client or self.client).post('/api/'+path,json=data,headers={'Origin':ORIGIN,'X-CSRF-Token':csrf or self.csrf})

    def key(self,dataset='private',client=None,csrf=None):
        response=self.post('shortcut-tokens',dict(label='My phone',dataset=dataset),client,csrf)
        self.assertEqual(response.status_code,201,response.json)
        return response.json

    def send(self,key,body=None,path='/json-import',headers=None):
        return self.remote.post(path,json=body if body is not None else self.body,headers={'Authorization':'Bearer '+key,**(headers or {})})

    def test_create_only_reveal_hash_storage_and_cookie_only_management(self):
        key=self.key()
        listed=self.client.get('/api/shortcut-tokens')
        self.assertEqual(listed.status_code,200)
        self.assertNotIn(key['token'],listed.text)
        self.assertNotIn('token_hash',listed.text)
        with ledger.connect() as con:
            self.assertNotEqual(con.execute('SELECT token_hash FROM shortcut_tokens').fetchone()[0],key['token'])
        self.assertEqual(self.client.post('/api/shortcut-tokens',json=dict(label='No CSRF',dataset='private'),headers={'Origin':ORIGIN}).status_code,403)
        self.assertEqual(self.remote.get('/api/shortcut-tokens',headers={'Authorization':'Bearer '+key['token']}).status_code,401)

    def test_one_step_success_retry_and_original_source_ownership(self):
        key=self.key();first=self.send(key['token'])
        self.assertEqual(first.status_code,201,first.json)
        again=self.send(key['token']);self.assertEqual(again.status_code,200,again.json)
        self.assertEqual(first.json['entry_ids'],again.json['entry_ids'])
        rows=self.client.get('/api/data').json['transactions'];self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['amount'],2450);self.assertTrue(rows[0]['has_shortcut_source'])
        source=self.client.get('/api/shortcut-source/'+str(rows[0]['id']))
        self.assertEqual(source.json['payload'],self.body)
        self.assertEqual(self.remote.get('/api/shortcut-source/'+str(rows[0]['id']),headers={'Authorization':'Bearer '+key['token']}).status_code,401)
        backup=self.client.get('/api/backup')
        try:
            with zipfile.ZipFile(io.BytesIO(backup.data)) as archive:
                data=archive.read('data.json')
                self.assertIn(b'server_shortcut_imports',data);self.assertNotIn(key['token'].encode(),data);self.assertNotIn(b'"shortcut_tokens"',data)
        finally:
            backup.close()

    def test_auth_origin_content_type_size_and_validation(self):
        key=self.key()['token']
        self.assertEqual(self.client.post('/json-import',json=self.body).status_code,401)  # no cookie fallback
        self.assertEqual(self.send('wrong').status_code,401)
        self.assertEqual(self.send(key,headers={'Origin':'https://elsewhere.example'}).status_code,403)
        self.assertEqual(self.remote.post('/json-import',data='{}',content_type='text/plain',headers={'Authorization':'Bearer '+key}).status_code,415)
        self.assertEqual(self.remote.post('/json-import',data='{bad',content_type='application/json',headers={'Authorization':'Bearer '+key}).status_code,400)
        self.assertEqual(self.send(key,{'timestamp':'invalid'}).status_code,422)
        self.assertEqual(self.send(key,{**self.body,'original_message':'x'*300000}).status_code,413)
        self.assertEqual(self.client.get('/api/data').json['transactions'],[])

    def test_token_cannot_use_general_actions_and_revoke_is_effective(self):
        key=self.key()
        self.assertEqual(self.send(key['token'],path='/api/transaction').status_code,403)
        self.assertEqual(self.send(key['token'],path='/api/transaction',headers={'Origin':ORIGIN}).status_code,401)
        self.assertEqual(self.remote.get('/api/data',headers={'Authorization':'Bearer '+key['token']}).status_code,401)
        self.assertEqual(self.post('shortcut-tokens/revoke',dict(id=key['id'])).status_code,200)
        self.assertEqual(self.send(key['token']).status_code,401)

    def test_fixed_dataset_and_multi_user_isolation(self):
        private=self.key();demo=self.key('demo')
        self.assertEqual(self.send(private['token'],path='/json-import?dataset=demo').status_code,403)
        self.assertEqual(self.send(demo['token']).status_code,201)
        self.assertEqual(self.client.get('/api/data').json['transactions'],[])
        self.assertEqual(self.post('users',dict(username='second',password=PASSWORD)).status_code,200)
        other=self.web.test_client();other_csrf=self.login(other,'second');second=self.key(client=other,csrf=other_csrf)
        self.assertEqual(self.send(second['token']).status_code,201)
        self.assertEqual(self.client.get('/api/data').json['transactions'],[])
        self.assertEqual(self.post('shortcut-tokens/revoke',dict(id=second['id'])).status_code,400)
        self.assertEqual(self.client.get('/api/shortcut-source/1').status_code,404)
        self.assertEqual(len(other.get('/api/data').json['transactions']),1)

    def test_password_change_invalidates_keys_and_deleted_entry_cannot_replay(self):
        key=self.key();saved=self.send(key['token'])
        self.assertEqual(saved.status_code,201)
        self.assertEqual(self.post('delete',dict(id=saved.json['entry_ids'][0])).status_code,200)
        self.assertEqual(self.send(key['token']).status_code,409)
        self.assertEqual(self.post('users/password',dict(current_password=PASSWORD,password=PASSWORD+'-new')).status_code,200)
        self.assertEqual(self.send(key['token']).status_code,401)

    def test_overscoped_fields_and_invalid_splits_do_not_partially_save(self):
        key=self.key()['token']
        for change in [dict(id=1),dict(user_id=2),dict(items=[dict(name='Part',amount='1')]),dict(category='Missing'),dict(amount=True)]:
            response=self.send(key,{**self.body,**change})
            self.assertEqual(response.status_code,422,response.json)
        self.assertEqual(self.client.get('/api/data').json['transactions'],[])

    def test_direct_income_uuid_conflict_and_documented_minimum(self):
        key=self.key()['token']
        minimum=dict(date='2026-10-19',merchant='Salary',amount='100',kind='income',request_id='11111111-1111-4111-8111-111111111111')
        first=self.send(key,minimum);self.assertEqual(first.status_code,201,first.json)
        self.assertEqual(self.send(key,minimum).status_code,200)
        self.assertEqual(self.send(key,{**minimum,'amount':'200'}).status_code,409)
        row=self.client.get('/api/data').json['transactions'][0]
        self.assertEqual((row['kind'],row['amount']),('income',-10000))
        for change in [dict(date='2026-02-30'),dict(ai={}),dict(merchant=''),dict(original_message='unused')]:
            self.assertEqual(self.send(key,{**self.body,**change}).status_code,422)

    def test_financial_restore_preserves_key_and_restores_retry_history(self):
        key=self.key()['token'];first=self.send(key)
        self.assertEqual(first.status_code,201)
        response=self.client.get('/api/backup')
        try:
            raw=response.data
        finally:
            response.close()
        self.post('delete',dict(id=first.json['entry_ids'][0]))
        self.assertEqual(self.send(key).status_code,409)
        restored=self.client.post('/api/backup-restore',data=raw,content_type='application/zip',headers={'Origin':ORIGIN,'X-CSRF-Token':self.csrf,'X-Backup-Confirm':'private'})
        self.assertEqual(restored.status_code,200,restored.json)
        retry=self.send(key)
        self.assertEqual(retry.status_code,200,retry.json)
        self.assertEqual(retry.json['entry_ids'],first.json['entry_ids'])
        self.assertEqual(len(self.client.get('/api/data').json['transactions']),1)
