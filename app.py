#!/usr/bin/env python3
import csv, datetime, hashlib, io, json, os, re, sqlite3
from contextlib import nullcontext
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('DATA_DIR', str(ROOT / 'data'))) / 'expenses.sqlite3'
CATEGORIES = ['Unkategorisiert', 'Lebensmittel', 'Wohnen', 'Küche & Haushalt', 'Fahrrad', 'Mobilität', 'Shopping', 'Freizeit', 'Ausgehen', 'Gesundheit', 'Abos', 'Reisen', 'Gehalt', 'Geschenke', 'Sonstige Einnahmen']

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
        CREATE TABLE IF NOT EXISTS category_aliases(alias TEXT PRIMARY KEY, name TEXT NOT NULL REFERENCES categories(name));
        CREATE TABLE IF NOT EXISTS payment_methods(name TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY, date TEXT NOT NULL, merchant TEXT NOT NULL, amount INTEGER NOT NULL, category TEXT NOT NULL REFERENCES categories(name), import_key TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE, name TEXT NOT NULL, amount INTEGER NOT NULL, category TEXT NOT NULL REFERENCES categories(name));
        CREATE TABLE IF NOT EXISTS receipt_images(transaction_id INTEGER PRIMARY KEY REFERENCES transactions(id) ON DELETE CASCADE, image BLOB NOT NULL);
        CREATE TABLE IF NOT EXISTS shortcut_imports(request_id TEXT PRIMARY KEY,transaction_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS account_settings(payment_method TEXT PRIMARY KEY REFERENCES payment_methods(name), share_bp INTEGER NOT NULL, share_income INTEGER NOT NULL, iban TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS transfer_links(outgoing_id INTEGER PRIMARY KEY REFERENCES transactions(id) ON DELETE CASCADE,incoming_id INTEGER UNIQUE NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,manual INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS transfer_ignored(outgoing_id INTEGER REFERENCES transactions(id) ON DELETE CASCADE,incoming_id INTEGER REFERENCES transactions(id) ON DELETE CASCADE,PRIMARY KEY(outgoing_id,incoming_id));
        ''')
        if 'group_name' not in {row['name'] for row in c.execute('PRAGMA table_info(transactions)')}:
            c.execute("ALTER TABLE transactions ADD COLUMN group_name TEXT NOT NULL DEFAULT ''")
        if 'group_name' not in {row['name'] for row in c.execute('PRAGMA table_info(items)')}:
            c.execute('ALTER TABLE items ADD COLUMN group_name TEXT DEFAULT NULL')
        if 'payment_method' not in {row['name'] for row in c.execute('PRAGMA table_info(transactions)')}:
            c.execute("ALTER TABLE transactions ADD COLUMN payment_method TEXT NOT NULL DEFAULT ''")
        if 'kind' not in {row['name'] for row in c.execute('PRAGMA table_info(transactions)')}:
            c.execute("ALTER TABLE transactions ADD COLUMN kind TEXT NOT NULL DEFAULT 'expense'")
        if 'notes' not in {row['name'] for row in c.execute('PRAGMA table_info(transactions)')}:
            c.execute("ALTER TABLE transactions ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
        if 'counterparty_iban' not in {row['name'] for row in c.execute('PRAGMA table_info(transactions)')}:
            c.execute("ALTER TABLE transactions ADD COLUMN counterparty_iban TEXT NOT NULL DEFAULT ''")
        for name in CATEGORIES:
            if not c.execute('SELECT 1 FROM category_aliases WHERE alias=?', (name,)).fetchone():
                c.execute('INSERT OR IGNORE INTO categories VALUES (?)', (name,))
                c.execute('INSERT INTO category_aliases VALUES (?,?)', (name, name))
        c.executemany('INSERT OR IGNORE INTO payment_methods VALUES (?)', [('Bar',), ('PayPal',)])
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

def save_transaction(d, db=None, *, _connection=None):
    receipt = None
    if 'receipt_image' in d:
        from receipts import prepare_jpeg
        receipt = prepare_jpeg(d['receipt_image'])
    remove_receipt = d.get('remove_receipt', False)
    if not isinstance(remove_receipt, bool):
        raise ValueError('Ungültige Belegeinstellung.')
    if receipt is not None and remove_receipt:
        raise ValueError('Beleg nicht gleichzeitig ersetzen und entfernen.')
    kind = d.get('kind', 'expense')
    if d.get('id') and 'kind' not in d:
        with (nullcontext(_connection) if _connection is not None else connect(db)) as con:
            row = con.execute('SELECT kind FROM transactions WHERE id=?', (int(d['id']),)).fetchone()
            if row:
                kind = row['kind']
    if kind not in ('expense', 'income'):
        raise ValueError('Unbekannter Buchungstyp.')
    amount = cents(d['amount'])
    if kind == 'income':
        amount = -abs(amount)
    merchant = str(d['merchant']).strip()
    if not merchant: raise ValueError('Bitte einen Händler eingeben.')
    date = date_value(d['date'])
    items = d.get('items', [])
    converted = []
    for item in items:
        group = item.get('group_name')
        if group is not None:
            if not isinstance(group, str) or len(group.strip()) > 80:
                raise ValueError('Gruppenname muss höchstens 80 Zeichen enthalten.')
            group = group.strip()
        item_amount = cents(item['amount'])
        if kind == 'income':
            item_amount = -abs(item_amount)
        converted.append((str(item['name']).strip(), item_amount, item['category'], group))
    if any(not x[0] for x in converted): raise ValueError('Jede Position benötigt einen Namen.')
    if converted and sum(x[1] for x in converted) != amount:
        raise ValueError('Die Summe der Positionen muss exakt dem Buchungsbetrag entsprechen.')
    with (nullcontext(_connection) if _connection is not None else connect(db)) as c:
        notes = d.get('notes')
        if 'notes' in d and (not isinstance(notes, str) or len(notes) > 4000):
            raise ValueError('Notizen dürfen höchstens 4000 Zeichen enthalten.')
        payment = d.get('payment_method')
        if 'payment_method' in d:
            if not isinstance(payment, str) or payment and not c.execute('SELECT 1 FROM payment_methods WHERE name=?', (payment,)).fetchone():
                raise ValueError('Unbekanntes Zahlungsmittel.')
        group_name = d.get('group_name')
        if 'group_name' in d:
            if not isinstance(group_name, str) or len(group_name.strip()) > 80:
                raise ValueError('Gruppenname muss höchstens 80 Zeichen enthalten.')
            group_name = group_name.strip()
        if d.get('id'):
            txid = int(d['id'])
            existing = c.execute('SELECT group_name,payment_method,notes FROM transactions WHERE id=?',(txid,)).fetchone()
            if not existing: raise ValueError('Buchung nicht gefunden.')
            if 'group_name' not in d:
                group_name = existing['group_name']
            if 'payment_method' not in d:
                payment = existing['payment_method']
            if 'notes' not in d:
                notes = existing['notes']
            c.execute('UPDATE transactions SET date=?,merchant=?,amount=?,category=? WHERE id=?',(date,merchant,amount,d['category'],txid))
            c.execute('DELETE FROM items WHERE transaction_id=?',(txid,))
        else:
            txid = c.execute('INSERT INTO transactions(date,merchant,amount,category) VALUES (?,?,?,?)',(date,merchant,amount,d['category'])).lastrowid
        c.execute('UPDATE transactions SET group_name=? WHERE id=?', (group_name or '', txid))
        c.execute('UPDATE transactions SET payment_method=? WHERE id=?', (payment or '', txid))
        c.execute('UPDATE transactions SET kind=? WHERE id=?', (kind, txid))
        c.execute('UPDATE transactions SET notes=? WHERE id=?', (notes or '', txid))
        c.executemany('INSERT INTO items(transaction_id,name,amount,category,group_name) VALUES (?,?,?,?,?)',[(txid,*x) for x in converted])
        if receipt is not None:
            c.execute('INSERT INTO receipt_images(transaction_id,image) VALUES (?,?) ON CONFLICT(transaction_id) DO UPDATE SET image=excluded.image', (txid, receipt))
        elif remove_receipt:
            c.execute('DELETE FROM receipt_images WHERE transaction_id=?', (txid,))
    return {'id': txid}

TR_HEADERS = {'datetime', 'date', 'account_type', 'category', 'type', 'name', 'amount', 'currency', 'transaction_id', 'counterparty_iban', 'description', 'asset_class'}
TR_TYPES = {'CARD_TRANSACTION', 'TRANSFER_INSTANT_OUTBOUND', 'TRANSFER_INSTANT_INBOUND', 'TRANSFER_OUTBOUND', 'TRANSFER_INBOUND'}

def trade_republic(headers):
    return TR_HEADERS.issubset(set(headers))

def tr_rows(rows, payment):
    """Only confirmed cash payment types; never infer investment/tax semantics."""
    result, excluded = [], []
    if not payment: raise ValueError('Für Trade Republic bitte ein Zahlungsmittel auswählen.')
    for index, row in enumerate(rows, 2):
        try:
            if row['category'] != 'CASH' or row['type'] not in TR_TYPES or row['asset_class'].strip():
                excluded.append({'line': index, 'type': row['type'], 'reason': 'Nicht unterstützte Buchungsart / Anlagebuchung'})
                continue
            if row['currency'] != 'EUR': raise ValueError('Nur EUR wird unterstützt')
            if not row['transaction_id'].strip(): raise ValueError('Transaktions-ID fehlt')
            value = cents(row['amount'])
            if not value:
                excluded.append({'line': index, 'type': row['type'], 'reason': 'Nullbetrag'})
                continue
            merchant = (row['name'].strip() or row.get('counterparty_name', '').strip() or row['description'].strip())
            if not merchant: raise ValueError('Bezeichnung fehlt')
            if len(merchant)>200: raise ValueError('Bezeichnung zu lang')
            day = date_value(row['date'])
            iban = re.sub(r'\s+', '', row['counterparty_iban']).upper()
            if len(iban)>34: raise ValueError('Gegenkonto zu lang')
            base = '\0'.join(['trade-republic', payment, row['account_type'].strip(), row['transaction_id'].strip()])
            key = 'tr:' + hashlib.sha256(base.encode()).hexdigest()
            result.append((day, merchant, -value, 'Unkategorisiert', key, '', iban))
        except (ValueError, KeyError, TypeError) as e:
            raise ValueError(f'CSV-Zeile {index}: {e}')
    return result, excluded

def csv_excluded(d):
    headers, rows = read_csv(d['text'])
    return tr_rows(rows, d.get('payment_method', ''))[1] if trade_republic(headers) else []

def _csv_plan(d, c):
    headers, rows = read_csv(d['text'])
    prepared, occurrences = [], {}
    if trade_republic(headers):
        prepared, _ = tr_rows(rows, d.get('payment_method', ''))
        rows = []
    for index, row in enumerate(rows, 2):
        try:
            date = date_value(row[d['date_column']])
            merchant = row[d['merchant_column']].strip()
            amount = cents(row[d['amount_column']]) * (-1 if d.get('bank_sign', True) else 1)
            if not merchant: raise ValueError('Händler fehlt')
            payment = d.get('payment_method', '')
            canonical = json.dumps([date,merchant,amount,payment],ensure_ascii=False)
            occurrences[canonical] = occurrences.get(canonical,0) + 1
            key = hashlib.sha256((canonical + ':' + str(occurrences[canonical])).encode()).hexdigest()
            legacy = json.dumps([date,merchant,amount],ensure_ascii=False)
            legacy_key = hashlib.sha256((legacy + ':' + str(occurrences[canonical])).encode()).hexdigest()
            counterpart = ''
            if d.get('counterparty_column'):
                counterpart = re.sub(r'\s+', '', str(row[d['counterparty_column']])).upper()
                if len(counterpart) > 34:
                    raise ValueError('Gegenkonto ist zu lang')
            prepared.append((date,merchant,amount,'Unkategorisiert',key,legacy_key,counterpart))
        except (ValueError, KeyError, TypeError) as e: raise ValueError(f'CSV-Zeile {index}: {e}')
    payment = d.get('payment_method', '')
    if not isinstance(payment, str) or payment and not c.execute('SELECT 1 FROM payment_methods WHERE name=?', (payment,)).fetchone():
        raise ValueError('Unbekanntes Zahlungsmittel.')
    category = c.execute("SELECT name FROM category_aliases WHERE alias='Unkategorisiert'").fetchone()[0]
    existing = {row['import_key']: row['payment_method'] for row in c.execute('SELECT import_key,payment_method FROM transactions WHERE import_key IS NOT NULL')}
    seen = set(existing)
    plan = []
    for date,merchant,amount,_,key,legacy_key,counterpart in prepared:
        if legacy_key in existing and existing[legacy_key] == payment:
            key = legacy_key
        duplicate = key in seen
        seen.add(key)
        plan.append({'values': (date,merchant,amount,category,key,payment,counterpart), 'duplicate': duplicate})
    return plan

def preview_import(d, db=None):
    """Read-only duplicate forecast; the committing import always rechecks."""
    with connect(db) as c:
        plan = _csv_plan(d, c)
    skipped = sum(row['duplicate'] for row in plan)
    return {'added': len(plan)-skipped, 'skipped': skipped, 'excluded': csv_excluded(d), 'rows': [
        {'date': row['values'][0], 'merchant': row['values'][1], 'amount': row['values'][2], 'duplicate': row['duplicate']}
        for row in plan[:20]]}

def import_csv(d, db=None):
    # Serialize duplicate checks with insertion, including concurrent browser imports.
    with connect(db) as c:
        c.execute('BEGIN IMMEDIATE')
        plan = _csv_plan(d, c)
        new = [row['values'] for row in plan if not row['duplicate']]
        c.executemany('INSERT INTO transactions(date,merchant,amount,category,import_key,payment_method,counterparty_iban) VALUES (?,?,?,?,?,?,?)', new)
    result = {'added': len(new), 'skipped': len(plan)-len(new)}
    excluded = csv_excluded(d)
    if excluded: result['excluded'] = excluded
    return result

def rename_category(old, new, db=None):
    if not isinstance(old, str) or not isinstance(new, str) or not new.strip() or len(new.strip()) > 60:
        raise ValueError('Kategorie muss 1–60 Zeichen enthalten.')
    new = new.strip()
    with connect(db) as con:
        if not con.execute('SELECT 1 FROM categories WHERE name=?', (old,)).fetchone():
            raise ValueError('Kategorie nicht gefunden.')
        if old == new:
            return {'ok': True}
        if con.execute('SELECT 1 FROM categories WHERE name=?', (new,)).fetchone():
            raise ValueError('Dieser Kategoriename ist bereits vergeben.')
        con.execute('INSERT INTO categories VALUES (?)', (new,))
        con.execute('UPDATE transactions SET category=? WHERE category=?', (new, old))
        con.execute('UPDATE items SET category=? WHERE category=?', (new, old))
        con.execute('UPDATE category_aliases SET name=? WHERE name=?', (new, old))
        con.execute('DELETE FROM categories WHERE name=?', (old,))
    return {'ok': True}

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
