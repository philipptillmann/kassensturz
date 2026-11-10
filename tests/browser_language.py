"""Optional free local browser check: python tests/browser_language.py.

Needs Playwright and a local Chromium executable. Uses disposable synthetic data;
never calls remote quote providers or builds/deploys the app.
"""
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as ledger
from server import create_app
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright


def run():
    previous = ledger.DB
    with tempfile.TemporaryDirectory() as folder:
        ledger.DB = Path(folder) / 'expenses.sqlite3'
        http = make_server('127.0.0.1', 0, create_app(password='browser-test-password', public_url=''))
        origin = 'http://127.0.0.1:' + str(http.server_port)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'), headless=True, args=['--no-sandbox'])
                page = browser.new_page(viewport={'width': 390, 'height': 844})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(origin + '/login')
                page.select_option('#language', 'en')
                page.wait_for_load_state('networkidle')
                assert page.locator('html').get_attribute('lang') == 'en'
                assert page.locator('#submit').inner_text() == 'Sign in'
                page.fill('#password', 'browser-test-password')
                page.click('#submit')
                page.wait_for_url(origin + '/')
                page.wait_for_function("() => document.querySelector('#appVersion').textContent.includes('Kassensturz')")
                page.select_option('#dataset', 'demo')
                page.wait_for_function("() => document.querySelector('#notice').textContent === 'Dataset: Demo.'")
                before = page.evaluate("fetch('/api/data?dataset=demo').then(r=>r.json())")
                for view, title in [('overview', 'Overview'), ('transactions', 'Entries'), ('graphs', 'Charts'), ('wealth', 'Wealth'), ('settings', 'Settings')]:
                    page.click('[data-view="' + view + '"]')
                    assert page.locator('#title').inner_text() == title
                assert page.locator('#paymentMethods').inner_text().find('Bank account') >= 0
                assert page.locator('#userManual').get_attribute('href') == '/manual/en'
                response = page.request.get(origin + '/manual/en')
                assert 'Kassensturz user manual' in response.text()
                page.select_option('#language', 'de')
                page.wait_for_load_state('networkidle')
                page.wait_for_function("() => document.querySelector('#appVersion').textContent.includes('Kassensturz')")
                assert page.locator('html').get_attribute('lang') == 'de'
                assert page.evaluate("fetch('/api/data?dataset=demo').then(r=>r.json())") == before
                page.click('[data-view="settings"]')
                assert page.locator('#userManual').get_attribute('href') == '/manual/de'
                page.select_option('#language', 'en')
                page.wait_for_load_state('networkidle')
                page.wait_for_function("() => document.querySelector('#appVersion').textContent.includes('Kassensturz')")
                page.select_option('#dataset', 'private')
                page.wait_for_function("() => document.querySelector('#notice').textContent === 'Dataset: Private.'")
                page.click('#add')
                assert page.locator('#editTitle').inner_text() == 'New entry'
                page.fill('#merchant', 'Ausgaben und Vermögen')
                page.fill('#amount', '60')
                page.select_option('#category', 'Shopping')
                page.fill('#entryNotes', 'Einstellungen bleiben unverändert')
                page.fill('#groupName', 'Buchungen')
                page.click('#save')
                page.wait_for_function("() => !document.querySelector('#editor').open")
                data = page.evaluate("fetch('/api/data?dataset=private').then(r=>r.json())")
                entry = data['transactions'][0]
                assert (entry['merchant'], entry['notes'], entry['group_name'], entry['amount']) == ('Ausgaben und Vermögen', 'Einstellungen bleiben unverändert', 'Buchungen', 6000)
                page.locator('#rows tr').first.click()
                assert page.locator('#merchant').input_value() == 'Ausgaben und Vermögen'
                assert page.locator('#entryNotes').input_value() == 'Einstellungen bleiben unverändert'
                assert not errors, errors
                browser.close()
                print('Browser checks passed: both languages, persistence, all main views, manuals, EUR entry creation, unchanged user data.')
        finally:
            http.shutdown()
            ledger.DB = previous


if __name__ == '__main__':
    run()
