"""Exercise fresh demo startup under a Windows-style text encoding."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class DemoEncodingTests(unittest.TestCase):
    def test_fresh_demo_with_cp1252_default_and_restart(self):
        # A child process releases SQLite handles before Windows removes the
        # directory. Emulate cp1252 on other operating systems as well.
        script = '''
import sys
from pathlib import Path
from unittest.mock import patch
import app as ledger
from datasets import prepare_demo

original_read = Path.read_text
def windows_read(path, encoding=None, errors=None):
    return original_read(path, encoding=encoding or 'cp1252', errors=errors)

db = Path(sys.argv[1]) / 'demo.sqlite3'
with patch.object(Path, 'read_text', windows_read):
    prepare_demo(db)
    with ledger.connect(db) as con:
        count = con.execute('SELECT count(*) FROM transactions').fetchone()[0]
        assert count > 0
        assert con.execute('SELECT count(*) FROM items').fetchone()[0] > 0
        assert not con.execute('PRAGMA foreign_key_check').fetchall()
        con.execute("UPDATE transactions SET merchant='Edited locally' WHERE id=1")
    prepare_demo(db)
    with ledger.connect(db) as con:
        assert con.execute('SELECT count(*) FROM transactions').fetchone()[0] == count
        assert con.execute('SELECT merchant FROM transactions WHERE id=1').fetchone()[0] == 'Edited locally'
        assert not con.execute('PRAGMA foreign_key_check').fetchall()
'''
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, '-c', script, tmp],
                                    cwd=Path(__file__).resolve().parents[1],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
