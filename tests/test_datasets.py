import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as ledger
from datasets import prepare_demo


class DemoUpgradeTests(unittest.TestCase):
    def test_extension_preserves_changes_and_only_runs_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / 'demo.sqlite3'
            private = Path(tmp) / 'expenses.sqlite3'
            ledger.init(private)
            ledger.save_transaction({'date': '2026-01-01', 'merchant': 'Private purchase',
                                     'amount': '42', 'category': 'Shopping'}, db=private)
            samples = json.loads((ledger.ROOT / 'sample-data/demo.json').read_text())
            original = [sample for sample in samples if not sample.get('seed_group')]
            with patch('datasets.json.loads', return_value=original):
                prepare_demo(demo)
            with ledger.connect(demo) as con:
                con.execute("UPDATE transactions SET merchant='My edited demo' WHERE id=1")
                con.execute('DELETE FROM transactions WHERE id=2')
            prepare_demo(demo)
            with ledger.connect(demo) as con:
                before = [tuple(row) for row in con.execute('SELECT * FROM transactions ORDER BY id')]
                self.assertEqual(len(before), len(samples) - 1)
                self.assertEqual(con.execute('SELECT merchant FROM transactions WHERE id=1').fetchone()[0], 'My edited demo')
                self.assertEqual(con.execute("SELECT count(*) FROM transactions WHERE merchant='Demo · Supermarkt' AND amount=6435").fetchone()[0], 0)
                self.assertEqual(con.execute('SELECT count(DISTINCT substr(date,1,7)) FROM transactions').fetchone()[0], 12)
            prepare_demo(demo)
            with ledger.connect(demo) as con:
                self.assertEqual(before, [tuple(row) for row in con.execute('SELECT * FROM transactions ORDER BY id')])
            with ledger.connect(private) as con:
                self.assertEqual([(row['merchant'], row['amount']) for row in con.execute('SELECT * FROM transactions')], [('Private purchase', 4200)])
