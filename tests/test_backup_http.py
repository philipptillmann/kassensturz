import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import app as ledger
import backups
from server import create_app

PASSWORD = 'local-backup-test-password'
ORIGIN = 'http://localhost'


class BackupHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous = ledger.DB
        ledger.DB = Path(self.tmp.name) / 'expenses.sqlite3'
        self.web = create_app(password=PASSWORD, public_url='')
        self.client = self.web.test_client()
        self.csrf = self.client.post('/api/login',json={'password':PASSWORD},headers={'Origin':ORIGIN}).json['csrf']
        self.tx = dict(date='2026-10-01',merchant='Owner gift',amount='12',category='Shopping',notes='Keep notes')
        self.post_json('transaction',self.tx)

    def tearDown(self):
        ledger.DB = self.previous
        self.tmp.cleanup()

    def post_json(self, action, data, client=None, csrf=None):
        return (client or self.client).post('/api/'+action,json=data,headers={'Origin':ORIGIN,'X-CSRF-Token':csrf or self.csrf})

    def upload(self, action, payload, dataset='private', confirm=None, headers=None):
        values = {'Origin':ORIGIN,'X-CSRF-Token':self.csrf}
        if confirm is not None:
            values['X-Backup-Confirm'] = confirm
        values.update(headers or {})
        return self.client.post('/api/'+action+'?dataset='+dataset,data=payload,content_type='application/zip',headers=values)

    def download(self, client=None, dataset='private'):
        response = (client or self.client).get('/api/backup?dataset='+dataset)
        self.assertEqual(response.status_code,200,response.get_data(as_text=True) if response.mimetype!='application/zip' else '')
        try:
            return response.data
        finally:
            response.close()

    def test_download_preview_restore_and_login_survives(self):
        raw = self.download()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            metadata = json.loads(archive.read('data.json'))
            self.assertEqual(metadata['entries'][0]['merchant'],'Owner gift')
            self.assertNotIn('users',metadata)
            self.assertNotIn('sessions',metadata)
        preview = self.upload('backup-preview',raw)
        self.assertEqual(preview.status_code,200,preview.json)
        self.assertEqual((preview.json['entries'],preview.json['target_dataset']),(1,'private'))
        self.post_json('transaction',{**self.tx,'merchant':'Later'})
        result = self.upload('backup-restore',raw,confirm='private')
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(len(self.client.get('/api/data').json['transactions']),1)
        self.assertEqual(self.client.get('/api/session').status_code,200)

    def test_auth_csrf_origin_confirmation_and_upload_limit(self):
        raw = self.download()
        self.assertEqual(self.web.test_client().get('/api/backup').status_code,401)
        self.assertEqual(self.upload('backup-preview',raw,headers={'X-CSRF-Token':'wrong'}).status_code,403)
        self.assertEqual(self.upload('backup-preview',raw,headers={'Origin':'https://elsewhere.example'}).status_code,403)
        self.assertEqual(self.upload('backup-restore',raw).status_code,400)
        self.assertEqual(self.upload('backup-restore',raw,confirm='demo').status_code,400)
        with patch.object(backups,'MAX_ARCHIVE_BYTES',10):
            self.assertEqual(self.upload('backup-preview',raw).status_code,413)
        self.assertEqual(len(self.client.get('/api/data').json['transactions']),1)

    def test_bad_upload_and_private_restore_do_not_change_demo(self):
        demo_before = self.client.get('/api/data?dataset=demo').json
        raw = self.download()
        self.assertEqual(self.upload('backup-restore',b'not a zip',confirm='private').status_code,400)
        self.assertEqual(self.upload('backup-restore',raw,confirm='private').status_code,200)
        self.assertEqual(self.client.get('/api/data?dataset=demo').json,demo_before)
        self.assertEqual(len(self.client.get('/api/data').json['transactions']),1)

    def test_named_user_backup_restore_preserves_other_users_and_credentials(self):
        self.assertEqual(self.post_json('users/migrate',dict(username='owner',password=PASSWORD)).status_code,200)
        self.csrf = self.client.post('/api/login',json={'username':'owner','password':PASSWORD},headers={'Origin':ORIGIN}).json['csrf']
        self.assertEqual(self.post_json('users',dict(username='second',password=PASSWORD)).status_code,200)
        other = self.web.test_client()
        token = other.post('/api/login',json={'username':'second','password':PASSWORD},headers={'Origin':ORIGIN}).json['csrf']
        self.post_json('transaction',{**self.tx,'merchant':'Second secret'},other,token)
        second_before = other.get('/api/data').json
        raw = self.download()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertNotIn('Second secret',archive.read('data.json').decode())
        with ledger.connect() as con:
            users_before = [tuple(r) for r in con.execute('SELECT * FROM users ORDER BY id')]
        self.assertEqual(self.upload('backup-restore',raw,confirm='private').status_code,200)
        self.assertEqual(other.get('/api/data').json,second_before)
        self.assertEqual(self.client.get('/api/session').json['user']['username'],'owner')
        with ledger.connect() as con:
            self.assertEqual([tuple(r) for r in con.execute('SELECT * FROM users ORDER BY id')],users_before)

    def test_large_request_and_staging_use_writable_data_directory(self):
        with ledger.connect() as con:
            con.execute('INSERT INTO receipt_images VALUES (?,?)',(1,b'\xff\xd8'+os.urandom(1_100_000)))
        before = {p.name for p in Path(self.tmp.name).iterdir()}
        # Force both spooled files to disk, and make the global temp fallback unusable.
        with patch('tempfile.tempdir','/missing-system-temp-directory'):
            raw = self.download()
            self.assertGreater(len(raw),1_000_000)
            self.assertEqual(self.upload('backup-preview',raw).status_code,200)
            self.assertEqual(self.upload('backup-restore',raw,confirm='private').status_code,200)
        self.assertEqual({p.name for p in Path(self.tmp.name).iterdir()},before)
