#!/usr/bin/env python3
import csv, datetime, hashlib, io, json, os, re, sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('DATA_DIR', str(ROOT / 'data'))) / 'expenses.sqlite3'
CATEGORIES = ['Unkategorisiert', 'Lebensmittel', 'Wohnen', 'Küche & Haushalt', 'Fahrrad', 'Mobilität', 'Shopping', 'Freizeit', 'Gesundheit', 'Abos', 'Reisen']

def connect(db=None):
    con = sqlite3.connect(DB if db is None else db, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    return con

def init(db=None):
    db = DB if db is None else Path(db)
    db.parent.mkdir(parents=True, exist_ok=True)
    with connect(db) as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires INTEGER NOT NULL, auth_version TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS categories(name TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY, date TEXT NOT NULL, merchant TEXT NOT NULL, amount INTEGER NOT NULL, category TEXT NOT NULL REFERENCES categories(name), import_key TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE, name TEXT NOT NULL, amount INTEGER NOT NULL, category TEXT NOT NULL REFERENCES categories(name));
        ''')
        c.executemany('INSERT OR IGNORE INTO categories VALUES (?)', [(x,) for x in CATEGORIES])
    os.chmod(db, 0o600)

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

def save_transaction(d, db=None):
    amount = cents(d['amount'])
    merchant = str(d['merchant']).strip()
    if not merchant: raise ValueError('Bitte einen Händler eingeben.')
    date = date_value(d['date'])
    items = d.get('items', [])
    converted = [(str(x['name']).strip(), cents(x['amount']), x['category']) for x in items]
    if any(not x[0] for x in converted): raise ValueError('Jede Position benötigt einen Namen.')
    if converted and sum(x[1] for x in converted) != amount:
        raise ValueError('Die Summe der Positionen muss exakt dem Buchungsbetrag entsprechen.')
    with connect(db) as c:
        if d.get('id'):
            txid = int(d['id'])
            if not c.execute('SELECT id FROM transactions WHERE id=?',(txid,)).fetchone(): raise ValueError('Buchung nicht gefunden.')
            c.execute('UPDATE transactions SET date=?,merchant=?,amount=?,category=? WHERE id=?',(date,merchant,amount,d['category'],txid))
            c.execute('DELETE FROM items WHERE transaction_id=?',(txid,))
        else:
            txid = c.execute('INSERT INTO transactions(date,merchant,amount,category) VALUES (?,?,?,?)',(date,merchant,amount,d['category'])).lastrowid
        c.executemany('INSERT INTO items(transaction_id,name,amount,category) VALUES (?,?,?,?)',[(txid,*x) for x in converted])
    return {'id': txid}

def import_csv(d, db=None):
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
    with connect(db) as c:
        before = c.total_changes
        c.executemany('INSERT OR IGNORE INTO transactions(date,merchant,amount,category,import_key) VALUES (?,?,?,?,?)',prepared)
        added = c.total_changes-before
    return {'added':added,'skipped':len(prepared)-added}

def recognize(d):
    from receipts import recognize_text
    text = recognize_text(d['image'])
    items = []
    for line in text.splitlines():
        match = re.match(r'^(.+?)\s+(-?\d+[.,]\d{2})\s*(?:€|EUR)?$',line.strip())
        if match and not re.search(r'summe|gesamt|total|mwst|ust|netto|brutto|zahlung|gegeben|rückgeld',match[1],re.I):
            items.append({'name':match[1], 'amount':cents(match[2])/100,'category':suggest_category(match[1])})
    return {'text':text,'items':items}

def suggest_category(name):
    rules = {
        'Fahrrad': r'fahrrad|fahrradlicht|kettenschmier|bike|fahrradhelm|fahrradschlauch|pedal|sattel',
        'Küche & Haushalt': r'küche|pfanne|kochtopf|teller|besteck|schneidebrett|spülmittel|kaffeetasse|wasserkocher',
        'Lebensmittel': r'milch|brot|butter|joghurt|käse|banane|tomate|nudeln',
        'Gesundheit': r'apotheke|verband|pflaster|zahnpasta',
    }
    return next((category for category,pattern in rules.items() if re.search(pattern,name,re.I)), 'Unkategorisiert')
