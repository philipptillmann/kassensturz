#!/usr/bin/env python3
import argparse, base64, csv, datetime, hashlib, io, json, os, re, secrets, socket, sqlite3, subprocess, sys, tempfile, webbrowser
from decimal import Decimal, InvalidOperation
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'data' / 'expenses.sqlite3'
CATEGORIES = ['Unkategorisiert', 'Lebensmittel', 'Wohnen', 'Küche & Haushalt', 'Fahrrad', 'Mobilität', 'Shopping', 'Freizeit', 'Gesundheit', 'Abos', 'Reisen']
TOKEN = secrets.token_urlsafe(24)
SESSIONS = set()

def connect():
    con = sqlite3.connect(DB, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    return con

def init():
    DB.parent.mkdir(exist_ok=True)
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS categories(name TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY, date TEXT NOT NULL, merchant TEXT NOT NULL, amount INTEGER NOT NULL, category TEXT NOT NULL REFERENCES categories(name), import_key TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE, name TEXT NOT NULL, amount INTEGER NOT NULL, category TEXT NOT NULL REFERENCES categories(name));
        ''')
        c.executemany('INSERT OR IGNORE INTO categories VALUES (?)', [(x,) for x in CATEGORIES])
    os.chmod(DB, 0o600)

def cents(value):
    s = str(value).strip().replace('€','').replace('EUR','').replace(' ','').replace('\u00a0','')
    if ',' in s: s = s.replace('.','').replace(',','.')
    try:
        d = Decimal(s)
        if not d.is_finite() or d != d.quantize(Decimal('.01')): raise ValueError('Betrag muss höchstens zwei Nachkommastellen haben.')
        return int(d * 100)
    except InvalidOperation: raise ValueError('Ungültiger Betrag: ' + str(value))

def date_value(s):
    for fmt in ('%Y-%m-%d','%d.%m.%Y','%d.%m.%y','%d/%m/%Y'):
        try: return datetime.datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError: pass
    raise ValueError('Datum nicht erkannt: ' + s)

def read_csv(text):
    try: dialect = csv.Sniffer().sniff(text[:8000], delimiters=';,\t')
    except csv.Error: raise ValueError('CSV-Trennzeichen nicht erkannt.')
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')), dialect=dialect)
    rows = list(reader)
    if not reader.fieldnames or not rows: raise ValueError('CSV enthält keine Buchungen.')
    return reader.fieldnames, rows

def save_transaction(d):
    amount = cents(d['amount'])
    merchant = str(d['merchant']).strip()
    if not merchant: raise ValueError('Bitte einen Händler eingeben.')
    date = date_value(d['date'])
    items = d.get('items', [])
    converted = [(str(x['name']).strip(), cents(x['amount']), x['category']) for x in items]
    if any(not x[0] for x in converted): raise ValueError('Jede Position benötigt einen Namen.')
    if converted and sum(x[1] for x in converted) != amount:
        raise ValueError('Die Summe der Positionen muss exakt dem Buchungsbetrag entsprechen.')
    with connect() as c:
        if d.get('id'):
            txid = int(d['id'])
            if not c.execute('SELECT id FROM transactions WHERE id=?',(txid,)).fetchone(): raise ValueError('Buchung nicht gefunden.')
            c.execute('UPDATE transactions SET date=?,merchant=?,amount=?,category=? WHERE id=?',(date,merchant,amount,d['category'],txid))
            c.execute('DELETE FROM items WHERE transaction_id=?',(txid,))
        else:
            txid = c.execute('INSERT INTO transactions(date,merchant,amount,category) VALUES (?,?,?,?)',(date,merchant,amount,d['category'])).lastrowid
        c.executemany('INSERT INTO items(transaction_id,name,amount,category) VALUES (?,?,?,?)',[(txid,*x) for x in converted])
    return {'id': txid}

def import_csv(d):
    _, rows = read_csv(d['text'])
    prepared, occurrences = [], {}
    for index, row in enumerate(rows, 2):
        try:
            date = date_value(row[d['date_column']])
            merchant = row[d['merchant_column']].strip()
            amount = cents(row[d['amount_column']]) * (-1 if d.get('bank_sign', True) else 1)
            if not merchant: raise ValueError('Händler fehlt')
            canonical = json.dumps([date,merchant,amount],ensure_ascii=False)
            occurrences[canonical] = occurrences.get(canonical,0) + 1
            key = hashlib.sha256((canonical + ':' + str(occurrences[canonical])).encode()).hexdigest()
            prepared.append((date,merchant,amount,'Unkategorisiert',key))
        except (ValueError, KeyError, TypeError) as e: raise ValueError(f'CSV-Zeile {index}: {e}')
    with connect() as c:
        before = c.total_changes
        c.executemany('INSERT OR IGNORE INTO transactions(date,merchant,amount,category,import_key) VALUES (?,?,?,?,?)',prepared)
        added = c.total_changes-before
    return {'added':added,'skipped':len(prepared)-added}

def recognize(d):
    raw = base64.b64decode(d['image'], validate=True)
    if len(raw) > 12_000_000: raise ValueError('Bild ist zu groß (maximal 12 MB).')
    if sys.platform != 'darwin': raise ValueError('Apple Vision ist nur auf macOS verfügbar. Positionen bitte manuell eingeben.')
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/'receipt'
        path.write_bytes(raw)
        result = subprocess.run(['swift',str(ROOT/'ocr.swift'),str(path)],capture_output=True,text=True,timeout=90)
    if result.returncode: raise ValueError('Texterkennung fehlgeschlagen. Prüfe, ob die Xcode Command Line Tools installiert sind, oder erfasse Positionen manuell.')
    items = []
    for line in result.stdout.splitlines():
        match = re.match(r'^(.+?)\s+(-?\d+[.,]\d{2})\s*(?:€|EUR)?$',line.strip())
        if match and not re.search(r'summe|gesamt|total|mwst|ust|netto|brutto|zahlung|gegeben|rückgeld',match[1],re.I):
            items.append({'name':match[1], 'amount':cents(match[2])/100,'category':suggest_category(match[1])})
    return {'text':result.stdout,'items':items}

def suggest_category(name):
    rules = {
        'Fahrrad': r'fahrrad|fahrradlicht|kettenschmier|bike|fahrradhelm|fahrradschlauch|pedal|sattel',
        'Küche & Haushalt': r'küche|pfanne|kochtopf|teller|besteck|schneidebrett|spülmittel|kaffeetasse|wasserkocher',
        'Lebensmittel': r'milch|brot|butter|joghurt|käse|banane|tomate|nudeln',
        'Gesundheit': r'apotheke|verband|pflaster|zahnpasta',
    }
    return next((category for category,pattern in rules.items() if re.search(pattern,name,re.I)), 'Unkategorisiert')

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass  # Verbindungslinks nicht protokollieren
    def send(self, value, status=200, content_type='application/json', cookie=None):
        data = json.dumps(value,ensure_ascii=False).encode() if content_type=='application/json' else value
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        if cookie: self.send_header('Set-Cookie',cookie)
        self.end_headers()
        self.wfile.write(data)
    def authorized(self):
        cookies = dict(part.strip().split('=',1) for part in self.headers.get('Cookie','').split(';') if '=' in part)
        return cookies.get('session') in SESSIONS
    def do_GET(self):
        url = urlparse(self.path)
        token = parse_qs(url.query).get('token',[''])[0]
        if token and secrets.compare_digest(token,TOKEN):
            session = secrets.token_urlsafe(32); SESSIONS.add(session)
            self.send_response(303); self.send_header('Location','/'); self.send_header('Set-Cookie',f'session={session}; HttpOnly; SameSite=Strict; Path=/'); self.end_headers(); return
        if not self.authorized():
            self.send(b'Bitte den Verbindungslink aus dem Terminal verwenden.',401,'text/plain; charset=utf-8'); return
        if url.path == '/api/data':
            with connect() as c:
                transactions = [dict(x) for x in c.execute('SELECT * FROM transactions ORDER BY date DESC,id DESC')]
                for t in transactions: t['items'] = [dict(x) for x in c.execute('SELECT * FROM items WHERE transaction_id=?',(t['id'],))]
                categories = [x[0] for x in c.execute('SELECT name FROM categories ORDER BY name')]
            self.send({'transactions':transactions,'categories':categories}); return
        if url.path == '/api/export':
            with connect() as c:
                out=io.StringIO(); writer=csv.writer(out,delimiter=';'); writer.writerow(['Datum','Händler','Betrag EUR','Kategorie','Position'])
                for t in c.execute('SELECT * FROM transactions ORDER BY date DESC'):
                    items=list(c.execute('SELECT * FROM items WHERE transaction_id=?',(t['id'],)))
                    for x in items or [t]:
                        merchant=t['merchant']; name=x['name'] if items else ''
                        safe=lambda s: "'"+s if s.startswith(('=','+','-','@','\t','\r')) else s
                        writer.writerow([t['date'],safe(merchant),f"{x['amount']/100:.2f}".replace('.',','),safe(x['category']),safe(name)])
            self.send(('\ufeff'+out.getvalue()).encode(),content_type='text/csv; charset=utf-8'); return
        files={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
        if url.path not in files: self.send({'error':'Nicht gefunden'},404); return
        name=files[url.path]
        mime={'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[name.split('.')[-1]]
        self.send((ROOT/'static'/name).read_bytes(),content_type=mime)
    def do_POST(self):
        if not self.authorized(): self.send({'error':'Bitte Verbindungslink erneut öffnen.'},401); return
        if self.headers.get('Origin') and self.headers['Origin'] != 'http://'+self.headers.get('Host',''):
            self.send({'error':'Ungültiger Ursprung'},403); return
        try:
            length=int(self.headers.get('Content-Length',0))
            if length > 17_000_000: raise ValueError('Datei zu groß.')
            if self.headers.get('Content-Type') != 'application/json': raise ValueError('JSON erwartet.')
            d=json.loads(self.rfile.read(length))
            if self.path == '/api/transaction': result=save_transaction(d)
            elif self.path == '/api/import-preview':
                headers,rows=read_csv(d['text']); result={'headers':headers,'rows':rows[:3],'count':len(rows)}
            elif self.path == '/api/import': result=import_csv(d)
            elif self.path == '/api/ocr': result=recognize(d)
            elif self.path == '/api/category':
                name=str(d['name']).strip()
                if not name or len(name)>60: raise ValueError('Kategorie muss 1–60 Zeichen enthalten.')
                with connect() as c: c.execute('INSERT OR IGNORE INTO categories VALUES (?)',(name,))
                result={'ok':True}
            elif self.path == '/api/delete':
                with connect() as c: c.execute('DELETE FROM transactions WHERE id=?',(int(d['id']),))
                result={'ok':True}
            else: self.send({'error':'Nicht gefunden'},404); return
            self.send(result)
        except (ValueError,KeyError,TypeError,sqlite3.IntegrityError) as e: self.send({'error':str(e)},400)
        except subprocess.TimeoutExpired: self.send({'error':'Texterkennung dauert zu lange. Bitte manuell erfassen.'},400)
        except Exception: self.send({'error':'Vorgang fehlgeschlagen. Bitte Eingabe prüfen.'},500)

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='Lokales Ausgabenbuch')
    parser.add_argument('--lan',action='store_true',help='Zugriff im eigenen WLAN erlauben')
    parser.add_argument('--open',action='store_true')
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args(); init()
    server=ThreadingHTTPServer(('0.0.0.0' if args.lan else '127.0.0.1',args.port),Handler)
    url=f'http://127.0.0.1:{args.port}/?token={TOKEN}'
    print('\nAusgabenbuch läuft. Mit Ctrl+C beenden.\nMac: '+url,flush=True)
    if args.lan:
        try: ip=subprocess.check_output(['ipconfig','getifaddr','en0'],text=True).strip()
        except Exception: ip=socket.gethostbyname(socket.gethostname())
        print(f'Handy im gleichen WLAN: http://{ip}:{args.port}/?token={TOKEN}\nNur im vertrauenswürdigen privaten WLAN nutzen: Verbindung ist HTTP.',flush=True)
    if args.open: webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: server.server_close()
