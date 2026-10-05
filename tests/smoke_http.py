"""Exercise the actual container HTTP stack. Run only against a disposable test instance."""
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request

origin = sys.argv[1].rstrip('/')

def client():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

def call(browser, path, data=None, csrf=''):
    request = urllib.request.Request(origin + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={'Origin': origin, 'Content-Type': 'application/json', 'X-CSRF-Token': csrf})
    with browser.open(request, timeout=10) as response:
        return json.load(response)

def login(browser):
    return call(browser, '/api/login', {'password': os.environ['APP_PASSWORD']})['csrf']

laptop, phone = client(), client()
try:
    call(laptop, '/api/data')
    raise AssertionError('Anonymous access must be denied')
except urllib.error.HTTPError as error:
    assert error.code == 401
csrf = login(laptop)
login(phone)
if '--verify-persistence' in sys.argv:
    assert any(t['merchant'] == 'CI persistence check' for t in call(phone, '/api/data')['transactions'])
else:
    call(laptop, '/api/transaction', {'date': '2026-10-05', 'merchant': 'CI persistence check', 'amount': '12.34', 'category': 'Fahrrad'}, csrf)
    assert call(phone, '/api/data')['transactions'][0]['amount'] == 1234
    call(laptop, '/api/logout', {}, csrf)
    assert call(phone, '/api/data')['transactions']
print('Container HTTP and persistence checks passed')
