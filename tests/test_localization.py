import tempfile
import unittest
from pathlib import Path
import app as ledger
from localization import english_catalog, translate_message
from server import create_app


class LocalizationTests(unittest.TestCase):
    def test_messages_preserve_user_supplied_suffix(self):
        self.assertEqual(translate_message('Bitte anmelden.', 'en'), 'Please sign in.')
        name = 'Ausgaben und Vermögen'
        self.assertEqual(translate_message('Ungültiger Betrag: ' + name, 'en'), 'Invalid amount: ' + name)
        self.assertEqual(translate_message(name, 'en'), name)
        self.assertEqual(translate_message('Bitte anmelden.', 'de'), 'Bitte anmelden.')
        self.assertEqual(translate_message('Bitte anmelden.', 'invalid'), 'Bitte anmelden.')

    def test_public_manuals_and_translations_and_error_language(self):
        previous = ledger.DB
        with tempfile.TemporaryDirectory() as folder:
            try:
                ledger.DB = Path(folder) / 'expenses.sqlite3'
                app = create_app(password='test-language-password', public_url='')
                client = app.test_client()
                for language, heading in [('en', 'Kassensturz user manual'), ('de', 'Kassensturz Benutzerhandbuch')]:
                    with client.get('/manual/' + language) as response:
                        self.assertEqual(response.status_code, 200)
                        self.assertIn(heading, response.text)
                        self.assertIn('lang="' + language + '"', response.text)
                self.assertEqual(client.get('/manual/fr').status_code, 302)
                with client.get('/translations.js') as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertIn('window.KassensturzEnglish', response.text)
                with client.get('/i18n.js') as response:
                    self.assertEqual(response.status_code, 200)
                original = client.get('/api/data').json['error']
                client.set_cookie('kassensturz_language', 'en')
                self.assertEqual(client.get('/api/data').json['error'], english_catalog().get(original, original))
            finally:
                ledger.DB = previous
