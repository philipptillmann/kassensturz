import tempfile
import unittest
from pathlib import Path

import app as ledger
from server import create_app

PASSWORD = 'test-password-for-kassensturz'


class UserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = ledger.DB
        ledger.DB = Path(self.tmp.name) / 'expenses.sqlite3'
        self.web = create_app(password=PASSWORD, public_url='')
        self.owner = self.web.test_client()
        self.other = self.web.test_client()

    def tearDown(self):
        ledger.DB = self.old
        self.tmp.cleanup()

    def login(self, client, name=None, password=PASSWORD):
        return client.post('/api/login', json={'username':name, 'password':password}, headers={'Origin':'http://localhost'})

    def post(self, client, path, data):
        csrf = client.get('/api/session').json['csrf']
        return client.post('/api/'+path, json=data, headers={'Origin':'http://localhost','X-CSRF-Token':csrf})

    def migrate(self):
        self.assertEqual(self.login(self.owner).status_code, 200)
        response = self.post(self.owner,'users/migrate',{'username':'Owner','password':PASSWORD})
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(self.login(self.owner,'owner').status_code,200)

    def test_migration_preserves_database_and_revokes_bootstrap(self):
        self.login(self.owner)
        self.login(self.other)
        data={'merchant':'Private gift','date':'2026-10-01','amount':'12','category':'Shopping','notes':'Keep me','group_name':'Gift','items':[{'name':'Gift part','amount':'12','category':'Shopping'}]}
        self.assertEqual(self.post(self.owner,'transaction',data).status_code,200)
        with ledger.connect() as con:
            con.execute('INSERT INTO receipt_images VALUES (?,?)',(1,b'private-jpeg'))
            before=[tuple(r) for r in con.execute('SELECT * FROM transactions')]
        self.assertEqual(self.post(self.owner,'users/migrate',{'username':'Owner','password':PASSWORD}).status_code,200)
        self.assertEqual(self.other.get('/api/data').status_code,401)
        self.assertEqual(self.login(self.other).status_code,401)
        self.assertFalse(self.other.get('/api/auth-status').json['needs_migration'])
        self.assertEqual(self.login(self.owner,'OWNER').status_code,200)
        self.assertEqual(self.owner.get('/api/receipt/1').data,b'private-jpeg')
        with ledger.connect() as con:
            self.assertEqual(before,[tuple(r) for r in con.execute('SELECT * FROM transactions')])
            self.assertNotIn(PASSWORD,con.execute('SELECT password_hash FROM users').fetchone()[0])
        self.assertEqual(self.post(self.owner,'users/migrate',{'username':'someone','password':PASSWORD}).status_code,409)
        token=self.owner.get_cookie('session').value
        restarted=create_app(password=PASSWORD+'changed',public_url='').test_client()
        restarted.set_cookie('session',token)
        self.assertEqual(restarted.get('/api/data').status_code,200)

    def test_isolation_permissions_and_password_change(self):
        self.migrate()
        self.assertEqual(self.post(self.owner,'users',{'username':'second','password':PASSWORD}).status_code,200)
        self.assertEqual(self.login(self.other,'second').status_code,200)
        self.assertEqual(self.other.get('/api/users').status_code,403)
        self.assertEqual(self.post(self.other,'users',{'username':'intruder','password':PASSWORD}).status_code,403)
        data={'merchant':'Owner secret','date':'2026-10-01','amount':'12','category':'Shopping'}
        self.assertEqual(self.post(self.owner,'transaction',data).status_code,200)
        self.assertEqual(self.post(self.owner,'category',{'name':'Secret category'}).status_code,200)
        with ledger.connect() as con:
            con.execute('INSERT INTO receipt_images VALUES (?,?)',(1,b'owner-image'))
        self.assertEqual(self.other.get('/api/data').json['transactions'],[])
        self.assertNotIn('Secret category',self.other.get('/api/data').json['categories'])
        self.assertNotIn('Owner secret',self.other.get('/api/export').text)
        self.assertEqual(self.other.get('/api/receipt/1').status_code,404)
        data['merchant']='Second secret'
        self.assertEqual(self.post(self.other,'transaction',data).status_code,200)
        self.assertEqual(self.other.get('/api/data').json['transactions'][0]['id'],1)
        self.assertEqual(self.owner.get('/api/data').json['transactions'][0]['merchant'],'Owner secret')
        self.assertEqual(self.post(self.other,'category?dataset=demo',{'name':'Second demo category'}).status_code,200)
        self.assertNotIn('Second demo category',self.owner.get('/api/data?dataset=demo').json['categories'])
        self.assertEqual(self.post(self.other,'users/password',{'current_password':'wrong','password':PASSWORD+'new'}).status_code,403)
        self.assertEqual(self.post(self.other,'users/password',{'current_password':PASSWORD,'password':PASSWORD+'new'}).status_code,200)
        self.assertEqual(self.other.get('/api/data').status_code,401)
        self.assertEqual(self.owner.get('/api/data').status_code,200)
        self.assertEqual(self.login(self.other,'second').status_code,401)
        self.assertEqual(self.login(self.other,'second',PASSWORD+'new').status_code,200)

    def test_user_validation_and_csrf(self):
        self.migrate()
        for name in ['../escape','ab','x/y']:
            self.assertEqual(self.post(self.owner,'users',{'username':name,'password':PASSWORD}).status_code,400)
        self.assertEqual(self.post(self.owner,'users',{'username':'OWNER','password':PASSWORD}).status_code,400)
        self.assertEqual(self.owner.post('/api/users',json={'username':'bad','password':PASSWORD},headers={'Origin':'http://localhost'}).status_code,403)
        self.assertEqual(self.post(self.owner,'users',{'username':'valid','password':'short'}).status_code,400)
