"""Password-protected, single-household WSGI application."""
import csv
import hashlib
import io
import os
import secrets
import sqlite3
import threading
import time
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, g, jsonify, make_response, request, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

import app as ledger
from datasets import prepare_demo
from receipts import OCRBusy

SESSION_SECONDS = 7 * 24 * 3600
MAX_BODY = 17_000_000


def configured_password():
    password_file = os.environ.get('APP_PASSWORD_FILE')
    password = Path(password_file).read_text().rstrip('\r\n') if password_file else os.environ.get('APP_PASSWORD', '')
    if len(password) < 12:
        raise RuntimeError('Set APP_PASSWORD (or APP_PASSWORD_FILE) to a password of at least 12 characters.')
    return password


def create_app(password=None, public_url=None):
    password = configured_password() if password is None else password
    if len(password) < 12:
        raise ValueError('Password must contain at least 12 characters.')
    public_url = (os.environ.get('PUBLIC_URL', '') if public_url is None else public_url).rstrip('/')
    if public_url:
        parsed = urlsplit(public_url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('PUBLIC_URL must be an origin, e.g. https://expenses.example.com (no path).')
    web = Flask(__name__, static_folder=None)
    web.config['MAX_CONTENT_LENGTH'] = MAX_BODY
    web.config['MAX_FORM_MEMORY_SIZE'] = 100_000
    if public_url:
        web.config['TRUSTED_HOSTS'] = [urlsplit(public_url).hostname, 'localhost', '127.0.0.1']
    secure = public_url.startswith('https://')
    password_hash = generate_password_hash(password)
    auth_version = hashlib.pbkdf2_hmac('sha256', password.encode(), b'kassensturz-session-version-v1', 600_000).hex()
    del password
    ledger.init()
    dataset_paths = {'private': ledger.DB, 'demo': ledger.DB.parent / 'demo.sqlite3'}
    prepare_demo(dataset_paths['demo'])
    login_attempts = deque(maxlen=20)
    login_lock = threading.Lock()

    def failure(message, status=400):
        return jsonify(error=message), status

    @web.before_request
    def access_control():
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            expected_origin = public_url or request.host_url.rstrip('/')
            if request.headers.get('Origin') != expected_origin:
                return failure('Ungültiger Ursprung. Bitte die konfigurierte Serveradresse verwenden.', 403)
            if not request.is_json:
                return failure('JSON erwartet.', 415)
        public_paths = {'/login', '/login.js', '/style.css', '/api/login', '/healthz', '/manifest.webmanifest',
                        '/icons/icon.svg', '/icons/icon-180.png', '/icons/icon-192.png', '/icons/icon-512.png'}
        if request.path in public_paths:
            return None
        token = request.cookies.get('session', '')
        row = None
        if token and len(token) <= 100:
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            with ledger.connect() as con:
                row = con.execute('SELECT * FROM sessions WHERE token_hash=? AND expires>? AND auth_version=?',
                                  (token_hash, int(time.time()), auth_version)).fetchone()
            if row:
                g.session_hash = token_hash
                g.csrf = row['csrf']
        if not row:
            if request.path.startswith('/api/'):
                return failure('Bitte anmelden.', 401)
            return web.redirect('/login')
        if request.method == 'POST' and not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), g.csrf):
            return failure('Sitzung ungültig. Bitte die Seite neu laden.', 403)
        dataset = request.args.get('dataset', 'private')
        if dataset not in dataset_paths:
            return failure('Unbekannter Datensatz.')
        g.dataset = dataset

    def data_connect():
        return ledger.connect(dataset_paths[g.dataset])

    @web.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        if secure:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    @web.errorhandler(HTTPException)
    def http_error(error):
        if error.code == 413:
            return failure('Datei zu groß (maximal 12 MB für Rechnungsbilder).', 413)
        return failure(error.description, error.code)

    @web.errorhandler(ValueError)
    @web.errorhandler(KeyError)
    @web.errorhandler(TypeError)
    @web.errorhandler(sqlite3.IntegrityError)
    def invalid_input(error):
        if isinstance(error, sqlite3.IntegrityError):
            return failure('Ungültige Kategorie oder Buchung.')
        return failure(str(error))

    @web.errorhandler(OCRBusy)
    def ocr_busy(error):
        return failure(str(error), 429)

    @web.errorhandler(Exception)
    def unexpected(error):
        web.logger.exception('Request failed')
        return failure('Vorgang fehlgeschlagen. Bitte erneut versuchen.', 500)

    @web.get('/healthz')
    def health():
        with ledger.connect() as con:
            con.execute('SELECT 1 FROM categories LIMIT 1').fetchone()
        return jsonify(status='ok')

    @web.get('/login')
    def login_page():
        return send_from_directory(ledger.ROOT / 'static', 'login.html')

    @web.get('/login.js')
    @web.get('/style.css')
    @web.get('/manifest.webmanifest')
    def public_asset():
        return send_from_directory(ledger.ROOT / 'static', request.path[1:])

    @web.get('/icons/<filename>')
    def icon(filename):
        return send_from_directory(ledger.ROOT / 'static' / 'icons', filename)

    @web.post('/api/login')
    def login():
        data = request.get_json()
        if not isinstance(data, dict) or not isinstance(data.get('password'), str) or len(data['password']) > 1024:
            return failure('Bitte ein gültiges Passwort eingeben.')
        now = time.time()
        # A global limit protects the shared password even behind a reverse proxy.
        with login_lock:
            while login_attempts and now - login_attempts[0] >= 60:
                login_attempts.popleft()
            if len(login_attempts) >= 20:
                response = jsonify(error='Zu viele Anmeldeversuche. Bitte eine Minute warten.')
                response.status_code = 429
                response.headers['Retry-After'] = '60'
                return response
            login_attempts.append(now)
        if not check_password_hash(password_hash, data['password']):
            return failure('Falsches Passwort.', 401)
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with ledger.connect() as con:
            con.execute('DELETE FROM sessions WHERE expires<=? OR auth_version!=?', (int(now), auth_version))
            old_token = request.cookies.get('session', '')
            if old_token:
                con.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(old_token.encode()).hexdigest(),))
            con.execute('INSERT INTO sessions VALUES (?,?,?,?)',
                        (hashlib.sha256(token.encode()).hexdigest(), csrf, int(now) + SESSION_SECONDS, auth_version))
        response = jsonify(csrf=csrf)
        response.set_cookie('session', token, max_age=SESSION_SECONDS, httponly=True, secure=secure, samesite='Strict', path='/')
        return response

    @web.get('/api/session')
    def session_info():
        return jsonify(csrf=g.csrf)

    @web.post('/api/logout')
    def logout():
        with ledger.connect() as con:
            con.execute('DELETE FROM sessions WHERE token_hash=?', (g.session_hash,))
        response = jsonify(ok=True)
        response.delete_cookie('session', path='/', secure=secure, httponly=True, samesite='Strict')
        return response

    @web.get('/')
    def index():
        return send_from_directory(ledger.ROOT / 'static', 'index.html')

    @web.get('/app.js')
    def javascript():
        return send_from_directory(ledger.ROOT / 'static', 'app.js')

    @web.get('/api/data')
    def data():
        with data_connect() as con:
            transactions = [dict(x) for x in con.execute('SELECT * FROM transactions ORDER BY date DESC,id DESC')]
            all_items = {}
            for item in con.execute('SELECT * FROM items ORDER BY id'):
                all_items.setdefault(item['transaction_id'], []).append(dict(item))
            for transaction in transactions:
                transaction['items'] = all_items.get(transaction['id'], [])
            categories = [x[0] for x in con.execute('SELECT name FROM categories ORDER BY name')]
        return jsonify(transactions=transactions, categories=categories, dataset=g.dataset)

    @web.get('/api/export')
    def export():
        out = io.StringIO()
        writer = csv.writer(out, delimiter=';')
        writer.writerow(['Datum', 'Händler', 'Betrag EUR', 'Kategorie', 'Position'])
        def safe(value):
            return "'" + value if value.startswith(('=', '+', '-', '@', '\t', '\r')) else value
        with data_connect() as con:
            for transaction in con.execute('SELECT * FROM transactions ORDER BY date DESC'):
                items = list(con.execute('SELECT * FROM items WHERE transaction_id=? ORDER BY id', (transaction['id'],)))
                for item in items or [transaction]:
                    writer.writerow([transaction['date'], safe(transaction['merchant']),
                                     f"{item['amount'] / 100:.2f}".replace('.', ','), safe(item['category']),
                                     safe(item['name']) if items else ''])
        response = make_response(('\ufeff' + out.getvalue()).encode())
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename=kassensturz-{g.dataset}.csv'
        return response

    @web.post('/api/<action>')
    def action(action):
        data = request.get_json()
        if not isinstance(data, dict):
            return failure('JSON-Objekt erwartet.')
        if action == 'transaction':
            result = ledger.save_transaction(data, db=dataset_paths[g.dataset])
        elif action == 'import-preview':
            columns, rows = ledger.read_csv(data['text'])
            result = {'headers': columns, 'rows': rows[:3], 'count': len(rows)}
        elif action == 'import':
            result = ledger.import_csv(data, db=dataset_paths[g.dataset])
        elif action == 'ocr':
            result = ledger.recognize(data)
        elif action == 'category':
            name = str(data['name']).strip()
            if not name or len(name) > 60:
                return failure('Kategorie muss 1–60 Zeichen enthalten.')
            with data_connect() as con:
                con.execute('INSERT OR IGNORE INTO categories VALUES (?)', (name,))
            result = {'ok': True}
        elif action == 'delete':
            with data_connect() as con:
                con.execute('DELETE FROM transactions WHERE id=?', (int(data['id']),))
            result = {'ok': True}
        else:
            return failure('Nicht gefunden.', 404)
        return jsonify(result)

    return web


if __name__ == '__main__':
    from waitress import serve
    application = create_app()
    port = int(os.environ.get('PORT', '8080'))
    print(f'Kassensturz listening on port {port}', flush=True)
    serve(application, host='0.0.0.0', port=port, threads=8,
          max_request_body_size=MAX_BODY, channel_timeout=120,
          clear_untrusted_proxy_headers=True, expose_tracebacks=False)
