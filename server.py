"""Authenticated WSGI application with isolated per-user financial databases."""
import csv
import hashlib
import io
import json
import os
import secrets
import sqlite3
import threading
import time
import tempfile
import datetime
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, g, jsonify, make_response, request, send_from_directory, send_file
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

import app as ledger
import accounts
import backups
import shortcut_api
import users
from datasets import prepare_demo
from receipts import OCRBusy

SESSION_SECONDS = 7 * 24 * 3600
REMEMBER_SECONDS = 90 * 24 * 3600
APP_VERSION = (ledger.ROOT / 'VERSION').read_text().strip()
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
    auth_db = Path(ledger.DB)
    users.init(auth_db)
    shortcut_api.init(auth_db)
    dataset_paths = {'private': ledger.DB, 'demo': ledger.DB.parent / 'demo.sqlite3'}
    prepare_demo(dataset_paths['demo'])
    # Apply additive category/schema migrations to every existing user's datasets.
    with ledger.connect(auth_db) as con:
        existing_users = con.execute('SELECT * FROM users WHERE owns_legacy=0').fetchall()
    for user in existing_users:
        for path in users.paths(auth_db, user).values():
            if path.exists():
                ledger.init(path)
    login_attempts = deque(maxlen=20)
    login_lock = threading.Lock()

    def failure(message, status=400):
        return jsonify(error=message), status

    @web.before_request
    def access_control():
        if request.path in ('/json-import','/json-options'):
            request.max_content_length = shortcut_api.MAX_BODY
            expected_method = 'GET' if request.path == '/json-options' else 'POST'
            if request.method != expected_method:
                return failure(expected_method + ' erwartet.', 405)
            expected_origin = public_url or request.host_url.rstrip('/')
            if request.headers.get('Origin') not in (None, expected_origin):
                return failure('Ungültiger Ursprung.', 403)
            if request.path == '/json-import' and not request.is_json:
                return failure('JSON erwartet.', 415)
            identity = shortcut_api.authenticate(auth_db, request.headers.get('Authorization'))
            if identity is None:
                response = jsonify(error='Gültiger Kurzbefehls-Schlüssel erforderlich.')
                response.status_code = 401
                response.headers['WWW-Authenticate'] = 'Bearer realm="Kassensturz Shortcuts"'
                return response
            g.user, g.dataset = identity
            if request.args.get('dataset', g.dataset) != g.dataset:
                return failure('Schlüssel gilt für einen anderen Datensatz.', 403)
            g.dataset_paths = users.paths(auth_db, g.user)
            return None
        backup_upload = request.path in ('/api/backup-preview', '/api/backup-restore')
        if backup_upload:
            request.max_content_length = backups.MAX_ARCHIVE_BYTES
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            expected_origin = public_url or request.host_url.rstrip('/')
            if request.headers.get('Origin') != expected_origin:
                return failure('Ungültiger Ursprung. Bitte die konfigurierte Serveradresse verwenden.', 403)
            if not request.is_json and not (backup_upload and request.mimetype in ('application/zip', 'application/octet-stream')):
                return failure('JSON oder eine ZIP-Sicherung erwartet.' if backup_upload else 'JSON erwartet.', 415)
        public_paths = {'/login', '/login.js', '/style.css', '/api/login', '/api/auth-status', '/healthz', '/manifest.webmanifest',
                        '/icons/icon.svg', '/icons/icon-180.png', '/icons/icon-192.png', '/icons/icon-512.png'}
        if request.path in public_paths:
            return None
        token = request.cookies.get('session', '')
        row = None
        if token and len(token) <= 100:
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            with ledger.connect(auth_db) as con:
                row = con.execute('SELECT * FROM sessions WHERE token_hash=? AND expires>?',
                                  (token_hash, int(time.time()))).fetchone()
                g.user = con.execute('SELECT * FROM users WHERE id=?', (row['user_id'],)).fetchone() if row and row['user_id'] else None
                named = con.execute('SELECT 1 FROM users LIMIT 1').fetchone()
                expected = users.version(g.user) if g.user else auth_version
                if row and (row['auth_version'] != expected or (named and not g.user)):
                    row = None
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
        g.dataset_paths = users.paths(auth_db, g.user)

    def data_connect():
        return ledger.connect(g.dataset_paths[g.dataset])

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
            return failure('Kurzbefehlsanfrage zu groß (maximal 256 KiB).' if request.path == '/json-import' else 'Sicherung zu groß (maximal 544 MB).' if request.path.startswith('/api/backup') else 'Datei zu groß (maximal 12 MB für Rechnungsbilder).', 413)
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
        with ledger.connect(auth_db) as con:
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
        remember = data.get('remember', False)
        if not isinstance(remember, bool):
            return failure('Ungültige Sitzungseinstellung.')
        session_seconds = REMEMBER_SECONDS if remember else SESSION_SECONDS
        now = time.time()
        # A global limit protects logins even behind a reverse proxy.
        with login_lock:
            while login_attempts and now - login_attempts[0] >= 60:
                login_attempts.popleft()
            if len(login_attempts) >= 20:
                response = jsonify(error='Zu viele Anmeldeversuche. Bitte eine Minute warten.')
                response.status_code = 429
                response.headers['Retry-After'] = '60'
                return response
            login_attempts.append(now)
        with ledger.connect(auth_db) as con:
            named = con.execute('SELECT 1 FROM users LIMIT 1').fetchone()
            username = data.get('username', '')
            user = con.execute('SELECT * FROM users WHERE username=?', (username.strip().lower(),)).fetchone() if isinstance(username, str) else None
        candidate_hash = user['password_hash'] if named and user else password_hash
        valid = check_password_hash(candidate_hash, data['password'])
        if not valid or (named and not user):
            return failure('Benutzername oder Passwort falsch.', 401)
        session_version = users.version(user) if named else auth_version
        user_id = user['id'] if named else None
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with ledger.connect(auth_db) as con:
            con.execute('DELETE FROM sessions WHERE expires<=?', (int(now),))
            if user_id is None and con.execute('SELECT 1 FROM users LIMIT 1').fetchone():
                return failure('Bitte mit Benutzername anmelden.', 401)
            old_token = request.cookies.get('session', '')
            if old_token:
                con.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(old_token.encode()).hexdigest(),))
            con.execute('INSERT INTO sessions(token_hash,csrf,expires,auth_version,user_id) VALUES (?,?,?,?,?)',
                        (hashlib.sha256(token.encode()).hexdigest(), csrf, int(now) + session_seconds, session_version, user_id))
        response = jsonify(csrf=csrf)
        response.set_cookie('session', token, max_age=session_seconds, httponly=True, secure=secure, samesite='Strict', path='/')
        return response

    @web.get('/api/session')
    def session_info():
        return jsonify(csrf=g.csrf, user=users.public(g.user), needs_migration=g.user is None, version=APP_VERSION)

    @web.get('/json-options')
    def shortcut_options():
        return jsonify(shortcut_api.options(g.dataset_paths[g.dataset]))

    @web.post('/json-import')
    def import_shortcut():
        try:
            result, status = shortcut_api.ingest(request.get_json(), g.dataset_paths[g.dataset])
            return jsonify(result), status
        except (shortcut_api.DeletedImport, shortcut_api.ImportConflict) as error:
            return failure(str(error), 409)
        except ValueError as error:
            return failure(str(error), 422)

    @web.route('/api/shortcut-tokens', methods=['GET', 'POST'])
    def shortcut_tokens():
        if g.user is None:
            return failure('Bitte zuerst ein Benutzerkonto anlegen.', 409)
        if request.method == 'GET':
            return jsonify(tokens=shortcut_api.token_list(auth_db, g.user))
        data = request.get_json()
        if not isinstance(data, dict):
            return failure('JSON-Objekt erwartet.')
        return jsonify(shortcut_api.create_token(auth_db, g.user, data)), 201

    @web.post('/api/shortcut-tokens/revoke')
    def revoke_shortcut_token():
        if g.user is None:
            return failure('Bitte zuerst ein Benutzerkonto anlegen.', 409)
        data = request.get_json()
        if not isinstance(data, dict):
            return failure('JSON-Objekt erwartet.')
        shortcut_api.revoke_token(auth_db, g.user, data.get('id'))
        return jsonify(ok=True)

    @web.get('/api/shortcut-source/<int:transaction_id>')
    def shortcut_source(transaction_id):
        with data_connect() as con:
            source = con.execute('SELECT payload,created_at FROM shortcut_imports WHERE transaction_id=?', (transaction_id,)).fetchone()
        if source is None:
            return failure('Kurzbefehlsquelle nicht gefunden.', 404)
        return jsonify(payload=json.loads(source['payload']),created_at=source['created_at'])

    @web.get('/api/auth-status')
    def auth_status():
        with ledger.connect(auth_db) as con:
            return jsonify(needs_migration=con.execute('SELECT 1 FROM users LIMIT 1').fetchone() is None)

    @web.post('/api/users/migrate')
    def migrate_user():
        if g.user is not None:
            return failure('Bereits einem Konto zugeordnet.', 409)
        users.create(auth_db, request.get_json(), migrate=True)
        response = jsonify(ok=True)
        response.delete_cookie('session', path='/', secure=secure, httponly=True, samesite='Strict')
        return response

    @web.route('/api/users', methods=['GET', 'POST'])
    def manage_users():
        if g.user is None or not g.user['is_admin']:
            return failure('Nur für Administratoren.', 403)
        if request.method == 'POST':
            users.create(auth_db, request.get_json())
        with ledger.connect(auth_db) as con:
            return jsonify(users=[users.public(row) for row in con.execute('SELECT * FROM users ORDER BY username')])

    @web.post('/api/users/password')
    def change_password():
        if g.user is None:
            return failure('Bitte zuerst ein Benutzerkonto anlegen.', 409)
        data = request.get_json()
        current = data.get('current_password', '')
        if not isinstance(current, str) or not check_password_hash(g.user['password_hash'], current):
            return failure('Aktuelles Passwort falsch.', 403)
        _, hashed = users.credentials({'username': g.user['username'], 'password': data.get('password')})
        with ledger.connect(auth_db) as con:
            con.execute('UPDATE users SET password_hash=? WHERE id=?', (hashed,g.user['id']))
            con.execute('DELETE FROM sessions WHERE user_id=?', (g.user['id'],))
        return jsonify(ok=True)

    @web.post('/api/logout')
    def logout():
        with ledger.connect(auth_db) as con:
            con.execute('DELETE FROM sessions WHERE token_hash=?', (g.session_hash,))
        response = jsonify(ok=True)
        response.delete_cookie('session', path='/', secure=secure, httponly=True, samesite='Strict')
        return response

    @web.get('/')
    def index():
        return send_from_directory(ledger.ROOT / 'static', 'index.html')

    @web.get('/app.js')
    @web.get('/charts.js')
    def javascript():
        return send_from_directory(ledger.ROOT / 'static', request.path[1:])

    @web.get('/api/data')
    def data():
        accounts.reconcile_transfers(g.dataset_paths[g.dataset])
        with data_connect() as con:
            transactions = [dict(x) for x in con.execute('SELECT transactions.*, EXISTS(SELECT 1 FROM receipt_images WHERE transaction_id=transactions.id) AS has_receipt, EXISTS(SELECT 1 FROM shortcut_imports WHERE transaction_id=transactions.id) AS has_shortcut_source FROM transactions ORDER BY date DESC,id DESC')]
            all_items = {}
            for item in con.execute('SELECT * FROM items ORDER BY id'):
                all_items.setdefault(item['transaction_id'], []).append(dict(item))
            for transaction in transactions:
                transaction['items'] = all_items.get(transaction['id'], [])
            categories = [x[0] for x in con.execute('SELECT name FROM categories ORDER BY name')]
            payments = [x[0] for x in con.execute('SELECT name FROM payment_methods ORDER BY name')]
            default_category = con.execute("SELECT name FROM category_aliases WHERE alias='Unkategorisiert'").fetchone()[0]
            account_settings = [dict(row) for row in con.execute('SELECT * FROM account_settings ORDER BY payment_method')]
            links = [dict(row) for row in con.execute('SELECT * FROM transfer_links')]
            rejected = [dict(row) for row in con.execute('SELECT * FROM transfer_ignored')]
            linked = {id for link in links for id in (link['outgoing_id'],link['incoming_id'])}
            candidates = [pair for pair in accounts.candidate_pairs(con) if pair['outgoing_id'] not in linked and pair['incoming_id'] not in linked]
            for transaction in transactions:
                transaction['internal_transfer'] = transaction['id'] in linked
        return jsonify(transactions=transactions, categories=categories, payment_methods=payments, payment_details=accounts.payment_details(g.dataset_paths[g.dataset]), default_category=default_category, accounts=account_settings, transfer_links=links, transfer_candidates=candidates, transfer_rejected=rejected, dataset=g.dataset)

    @web.get('/api/receipt/<int:transaction_id>')
    def receipt_image(transaction_id):
        with data_connect() as con:
            row = con.execute('SELECT image FROM receipt_images WHERE transaction_id=?', (transaction_id,)).fetchone()
        if row is None:
            return failure('Kein Beleg vorhanden.', 404)
        response = make_response(bytes(row['image']))
        response.headers['Content-Type'] = 'image/jpeg'
        response.headers['Content-Disposition'] = f'inline; filename=kassensturz-beleg-{transaction_id}.jpg'
        return response

    @web.get('/api/backup')
    def download_backup():
        output = tempfile.SpooledTemporaryFile(max_size=1_000_000, dir=g.dataset_paths[g.dataset].parent)
        try:
            backups.write_archive(g.dataset_paths[g.dataset], output, dataset=g.dataset)
            size = output.tell()
            output.seek(0)
            response = send_file(output, mimetype='application/zip', as_attachment=True,
                                 download_name=f'kassensturz-{g.dataset}-{datetime.date.today()}.zip')
            response.content_length = size
            response.call_on_close(output.close)
            return response
        except BaseException:
            output.close()
            raise

    @web.post('/api/backup-preview')
    @web.post('/api/backup-restore')
    def upload_backup():
        restoring = request.path.endswith('backup-restore')
        if restoring and request.headers.get('X-Backup-Confirm') != g.dataset:
            return failure('Wiederherstellen des ausgewählten Datensatzes bitte bestätigen.')
        with tempfile.SpooledTemporaryFile(max_size=1_000_000, dir=g.dataset_paths[g.dataset].parent) as upload:
            size = 0
            while True:
                chunk = request.stream.read(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > backups.MAX_ARCHIVE_BYTES:
                    return failure('Sicherung zu groß (maximal 544 MB).', 413)
                upload.write(chunk)
            upload.seek(0)
            if restoring:
                result = backups.restore(upload, g.dataset_paths[g.dataset])
            else:
                result = backups.preview(upload, temp_dir=g.dataset_paths[g.dataset].parent)
            result['target_dataset'] = g.dataset
            return jsonify(result)

    @web.get('/api/export')
    def export():
        out = io.StringIO()
        writer = csv.writer(out, delimiter=';')
        writer.writerow(['Datum', 'Händler', 'Betrag EUR', 'Kategorie', 'Position', 'Gruppe', 'Zahlungsmittel', 'Buchungstyp', 'Notizen'])
        def safe(value):
            return "'" + value if value.startswith(('=', '+', '-', '@', '\t', '\r')) else value
        with data_connect() as con:
            for transaction in con.execute('SELECT * FROM transactions ORDER BY date DESC'):
                items = list(con.execute('SELECT * FROM items WHERE transaction_id=? ORDER BY id', (transaction['id'],)))
                for item in items or [transaction]:
                    writer.writerow([transaction['date'], safe(transaction['merchant']),
                                     f"{item['amount'] / 100:.2f}".replace('.', ','), safe(item['category']),
                                     safe(item['name']) if items else '',
                                     safe(transaction['group_name'] if not items or item['group_name'] is None else item['group_name']), safe(transaction['payment_method']),
                                     'Einnahme' if transaction['kind'] == 'income' else 'Ausgabe / Erstattung', safe(transaction['notes'])])
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
            result = ledger.save_transaction(data, db=g.dataset_paths[g.dataset])
        elif action == 'import-preview':
            columns, rows = ledger.read_csv(data['text'])
            result = {'headers': columns, 'rows': rows[:3], 'count': len(rows), 'source_accounts': ledger.volksbank_accounts(rows) if ledger.volksbank_format(columns) else [], 'provider': 'volksbank' if ledger.volksbank_format(columns) else ('ing' if ledger.ing_format(columns) else ('trade-republic' if ledger.trade_republic(columns) else None))}
        elif action == 'import-undo-preview':
            result = ledger.last_csv_import(db=g.dataset_paths[g.dataset])
        elif action == 'import-undo':
            result = ledger.revert_csv_import(data.get('token'), db=g.dataset_paths[g.dataset])
        elif action == 'import-check':
            result = ledger.preview_import(data, db=g.dataset_paths[g.dataset])
        elif action == 'import':
            result = ledger.import_csv(data, db=g.dataset_paths[g.dataset])
        elif action == 'ocr':
            result = ledger.recognize(data)
            with data_connect() as con:
                aliases = dict(con.execute('SELECT alias,name FROM category_aliases'))
            for item in result['items']:
                item['category'] = aliases.get(item['category'], item['category'])
        elif action == 'category-rename':
            result = ledger.rename_category(data['old_name'], data['name'], db=g.dataset_paths[g.dataset])
        elif action == 'account':
            result = accounts.configure_account(data, g.dataset_paths[g.dataset])
        elif action == 'transfer-confirm':
            result = accounts.confirm_transfer(data, g.dataset_paths[g.dataset])
        elif action == 'transfer-reject':
            result = accounts.reject_transfer(data, g.dataset_paths[g.dataset])
        elif action == 'transfer-reconsider':
            with data_connect() as con:
                con.execute('DELETE FROM transfer_ignored WHERE outgoing_id=? AND incoming_id=?', (int(data['outgoing_id']),int(data['incoming_id'])))
            accounts.reconcile_transfers(g.dataset_paths[g.dataset])
            result = {'ok': True}
        elif action == 'payment':
            result = accounts.configure_payment(data, g.dataset_paths[g.dataset])
        elif action == 'payment-method':
            name = data.get('name')
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 60:
                return failure('Zahlungsmittel muss 1–60 Zeichen enthalten.')
            with data_connect() as con:
                con.execute('INSERT OR IGNORE INTO payment_methods VALUES (?)', (name.strip(),))
            result = {'ok': True}
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
          max_request_body_size=backups.MAX_ARCHIVE_BYTES, channel_timeout=120,
          clear_untrusted_proxy_headers=True, expose_tracebacks=False)
