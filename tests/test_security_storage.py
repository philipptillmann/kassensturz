import os
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(importlib.util.find_spec('sqlcipher3') and Path('/dev/shm').is_dir(), 'SQLCipher and Linux RAM scratch required')
class StorageSecurityTests(unittest.TestCase):
    def run_code(self, code, env, success=True):
        result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,env={**os.environ,**env},capture_output=True,text=True)
        if success:self.assertEqual(result.returncode,0,result.stderr)
        else:self.assertNotEqual(result.returncode,0)
        return result
    def test_encryption_auth_receipts_wealth_backup_and_wrong_key(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);key=root/'key';key.write_text('ab'*32);key.chmod(0o600)
            data=root/'data';env={'DATA_DIR':str(data),'DATA_ENCRYPTION_KEY_FILE':str(key),'ENCRYPTED_TMPDIR':'/dev/shm'}
            self.run_code("""
import app,io,backups,sqlite3
from server import create_app
web=create_app(password='test-password-security',public_url='')
with app.connect() as c:
 c.execute("INSERT INTO payment_methods VALUES ('Private marker')")
 id=c.execute("INSERT INTO transactions(date,merchant,amount,category) VALUES ('2026-10-31','Secret purchase',123,'Shopping')").lastrowid
 c.execute('INSERT INTO receipt_images VALUES (?,?)',(id,b'\\xff\\xd8Secret receipt'))
import wealth
wealth.update(app.DB,dict(op='asset',name='Secret wealth',type='savings',value=10000,date='2026-10-31',rate_bp=0,maturity=''))
assert app.DB.read_bytes()[:16]!=b'SQLite format 3\\0'
for p in app.DB.parent.rglob('*'):
 if p.is_file():
  assert all(marker not in p.read_bytes() for marker in (b'Secret purchase',b'Secret receipt',b'Secret wealth'))
try:
 c=sqlite3.connect(app.DB);c.execute('SELECT * FROM transactions');raise AssertionError('plaintext read succeeded')
except sqlite3.DatabaseError: pass
out=io.BytesIO();backups.write_archive(app.DB,out,dataset='private');backups.restore(io.BytesIO(out.getvalue()),app.DB)
assert app.connect().execute('SELECT merchant FROM transactions').fetchone()[0]=='Secret purchase'
""",env)
            key.write_text('cd'*32)
            self.run_code('import app; app.init()',env,False)
            self.run_code('import app; app.init()', {**env,'DATA_ENCRYPTION_KEY_FILE':''},False)
    def test_offline_copy_migration_decryption_and_bad_key_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';key=root/'key';encrypted=root/'encrypted';plain=root/'plain'
            self.run_code("import app; app.init(); c=app.connect(); c.execute(\"INSERT INTO payment_methods VALUES ('Migration marker')\");c.commit();c.close()", {'DATA_DIR':str(source),'DATA_ENCRYPTION_KEY_FILE':''})
            subprocess.run([sys.executable,'tools/encrypt_data.py','--key-file',str(key),'--generate-key'],cwd=ROOT,check=True)
            original=(source/'expenses.sqlite3').read_bytes()
            for dest,src,decrypt in [(encrypted,source,False),(plain,encrypted,True)]:
                command=[sys.executable,'tools/encrypt_data.py','--key-file',str(key),'--source',str(src),'--destination',str(dest)]
                if decrypt:command+=['--decrypt']
                r=subprocess.run(command,cwd=ROOT,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual((source/'expenses.sqlite3').read_bytes(),original)
            self.run_code("import sqlite3; c=sqlite3.connect(r'"+str(plain/'expenses.sqlite3')+"');assert c.execute(\"SELECT name FROM payment_methods WHERE name='Migration marker'\").fetchone()",{'DATA_ENCRYPTION_KEY_FILE':''})
            key.chmod(0o644)
            self.run_code('import storage',{'DATA_ENCRYPTION_KEY_FILE':str(key)},False)
    def test_encryption_requires_ram_scratch(self):
        with tempfile.TemporaryDirectory() as folder:
            key=Path(folder)/'key';key.write_text('12'*32);key.chmod(0o600)
            self.run_code('import storage;storage.temporary_directory()',{'DATA_ENCRYPTION_KEY_FILE':str(key),'ENCRYPTED_TMPDIR':''},False)

class HttpsSecurityTests(unittest.TestCase):
    def test_production_requires_https_and_rejects_plaintext_mutations(self):
        import app
        from server import create_app
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'DB',Path(folder)/'expenses.sqlite3'):
            with patch.dict(os.environ,{'PUBLIC_URL':'','ALLOW_HTTP':'0'}):
                with self.assertRaises(ValueError):create_app(password='test-password-security')
            with patch.dict(os.environ,{'PUBLIC_URL':'https://money.example:443','ALLOW_HTTP':'0'}):
                web=create_app(password='test-password-security');client=web.test_client()
                r=client.get('/login',base_url='http://money.example');self.assertEqual(r.status_code,308);self.assertEqual(r.location,'https://money.example/login')
                self.assertEqual(client.post('/api/login',json={'password':'test-password-security'},base_url='http://money.example').status_code,426)
                r=client.post('/api/login',json={'password':'test-password-security'},base_url='http://money.example',headers={'X-Forwarded-Proto':'https','Origin':'https://money.example'})
                self.assertEqual(r.status_code,200,r.json);self.assertIn('Secure',r.headers['Set-Cookie']);self.assertIn('Strict-Transport-Security',r.headers)
                self.assertEqual(client.get('/healthz',base_url='http://localhost').status_code,200)
