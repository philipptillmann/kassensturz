"""User-scoped Kassensturz entry creation for Shortcuts and other JSON clients."""
from contextlib import closing
import datetime
from decimal import Decimal
import hashlib
import json
import re
import secrets
import time
import uuid

import app as ledger

MAX_BODY = 256 * 1024


class DeletedImport(ValueError):
    pass


class ImportConflict(ValueError):
    pass


def init(auth_db):
    with ledger.connect(auth_db) as con:
        con.execute('''CREATE TABLE IF NOT EXISTS shortcut_tokens(
            id INTEGER PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            label TEXT NOT NULL, dataset TEXT NOT NULL, auth_version TEXT NOT NULL,
            created_at INTEGER NOT NULL, last_used_at INTEGER, revoked_at INTEGER)''')


def user_version(user):
    return hashlib.sha256(user['password_hash'].encode()).hexdigest()


def token_list(auth_db, user):
    version = user_version(user)
    with ledger.connect(auth_db) as con:
        rows = con.execute('SELECT id,label,dataset,created_at,last_used_at,revoked_at,auth_version FROM shortcut_tokens WHERE user_id=? ORDER BY id DESC LIMIT 100', (user['id'],)).fetchall()
    return [dict(id=r['id'],label=r['label'],dataset=r['dataset'],created_at=r['created_at'],last_used_at=r['last_used_at'],active=r['revoked_at'] is None and r['auth_version']==version) for r in rows]


def create_token(auth_db, user, data):
    label = text(data.get('label'), 'Name', 80, required=True)
    dataset = data.get('dataset', 'private')
    if dataset not in ('private', 'demo'):
        raise ValueError('Unbekannter Datensatz.')
    token = 'kst_' + secrets.token_urlsafe(32)
    with ledger.connect(auth_db) as con:
        con.execute('BEGIN IMMEDIATE')
        if con.execute('SELECT count(*) FROM shortcut_tokens WHERE user_id=? AND revoked_at IS NULL AND auth_version=?', (user['id'],user_version(user))).fetchone()[0] >= 20:
            raise ValueError('Höchstens 20 aktive Kurzbefehls-Schlüssel. Alte Schlüssel zuerst widerrufen.')
        key_id = con.execute('INSERT INTO shortcut_tokens(token_hash,user_id,label,dataset,auth_version,created_at) VALUES (?,?,?,?,?,?)',
                             (hashlib.sha256(token.encode()).hexdigest(),user['id'],label,dataset,user_version(user),int(time.time()))).lastrowid
    return {'id': key_id, 'token': token, 'dataset': dataset, 'label': label}


def revoke_token(auth_db, user, key_id):
    if type(key_id) is not int or key_id < 1:
        raise ValueError('Ungültiger Schlüssel.')
    with ledger.connect(auth_db) as con:
        if con.execute('UPDATE shortcut_tokens SET revoked_at=? WHERE id=? AND user_id=?', (int(time.time()),key_id,user['id'])).rowcount != 1:
            raise ValueError('Schlüssel nicht gefunden.')


def authenticate(auth_db, authorization):
    match = re.fullmatch(r'Bearer (kst_[A-Za-z0-9_-]{43})', authorization or '', re.IGNORECASE)
    if not match:
        return None
    digest = hashlib.sha256(match[1].encode()).hexdigest()
    with ledger.connect(auth_db) as con:
        key = con.execute('SELECT * FROM shortcut_tokens WHERE token_hash=? AND revoked_at IS NULL', (digest,)).fetchone()
        if not key:
            return None
        user = con.execute('SELECT * FROM users WHERE id=?', (key['user_id'],)).fetchone()
        if not user or not secrets.compare_digest(key['auth_version'], user_version(user)):
            return None
        con.execute('UPDATE shortcut_tokens SET last_used_at=? WHERE id=?', (int(time.time()),key['id']))
    return user, key['dataset']


def text(value, field, maximum, required=False):
    if not isinstance(value, str) or len(value) > maximum or required and not value.strip():
        raise ValueError(f'{field}: Text mit {1 if required else 0}–{maximum} Zeichen erwartet.')
    return value


def request_id(body):
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'kassensturz-json-import-v1:' + digest)), canonical


def legacy_envelope(body):
    if not isinstance(body, dict) or set(body) != {'timestamp','original_message','ai'}:
        raise ValueError('Genau timestamp, original_message und ai werden erwartet.')
    stamp = text(body['timestamp'], 'timestamp', 64, True)
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})', stamp):
        raise ValueError('timestamp muss ISO 8601 mit Zeitzone sein.')
    parsed = datetime.datetime.fromisoformat(stamp.replace('Z','+00:00'))
    text(body['original_message'], 'original_message', 10000)
    ai = body['ai']
    if isinstance(ai, str):
        text(ai, 'ai', MAX_BODY)
        raw = ai.strip()
        fenced = re.fullmatch(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL | re.IGNORECASE)
        if fenced:
            raw = fenced[1].strip()
        try:
            ai = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(f'ai: Ungültiges JSON in Zeile {error.lineno}, Spalte {error.colno}.') from None
    if not isinstance(ai, dict):
        raise ValueError('ai muss ein JSON-Objekt oder dessen JSON-Text sein.')
    identity, canonical = request_id(body)
    return parsed.date().isoformat(), ai, identity, canonical


ENTRY_FIELDS = {'date','merchant','amount','currency','kind','category','payment_method','notes','group_name','items','request_id'}

def envelope(body):
    # Retain old clients and archived request fingerprints; new clients send entries directly.
    if isinstance(body, dict) and set(body) == {'timestamp','original_message','ai'}:
        return legacy_envelope(body)
    if not isinstance(body, dict):
        raise ValueError('Ein JSON-Objekt mit date, merchant und amount wird erwartet.')
    unknown = set(body) - ENTRY_FIELDS
    if unknown:
        raise ValueError('Unbekannte Buchungsfelder: ' + ', '.join(sorted(unknown)))
    day = text(body.get('date'), 'date', 10, True)
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
        raise ValueError('date muss JJJJ-MM-TT sein.')
    datetime.date.fromisoformat(day)
    # Validate required entry fields before looking up a retry.
    text(body.get('merchant'), 'merchant', 200, True)
    amount = money(body.get('amount'))
    if not amount: raise ValueError('Betrag darf nicht null sein.')
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    client_id = body.get('request_id')
    if 'request_id' in body:
        try:
            client_id = str(uuid.UUID(text(client_id, 'request_id', 36, True)))
        except (ValueError, AttributeError):
            raise ValueError('request_id muss eine UUID sein.') from None
        seed = 'request:' + client_id
    else:
        seed = 'payload:' + hashlib.sha256(canonical.encode()).hexdigest()
    identity = str(uuid.uuid5(uuid.NAMESPACE_URL, 'kassensturz-entry-v2:' + seed))
    return day, {key:value for key,value in body.items() if key not in ('date','request_id')}, identity, canonical


def money(raw):
    if isinstance(raw, bool) or not isinstance(raw, (str,int,float)):
        raise ValueError('Betrag als EUR-Zahl oder Dezimaltext erwartet.')
    value = ledger.cents(raw)
    if not -99999999999 <= value <= 99999999999:
        raise ValueError('Betrag ist zu groß.')
    return value


def legacy_transaction(ai, day, con, max_notes=2000):
    allowed = {'title','amount','currency','category','payment_method','notes','group_name','items'}
    if set(ai) - allowed:
        raise ValueError('Unbekannte ai-Felder: ' + ', '.join(sorted(set(ai)-allowed)))
    title = text(ai.get('title'), 'title', 200, True).strip()
    amount = money(ai.get('amount'))
    if not amount:
        raise ValueError('Betrag darf nicht null sein.')
    if ai.get('currency', 'EUR') != 'EUR':
        raise ValueError('Nur currency EUR wird unterstützt; keine Währungsumrechnung.')
    categories = {r[0] for r in con.execute('SELECT name FROM categories')}
    aliases = dict(con.execute('SELECT alias,name FROM category_aliases'))
    def category(value):
        name = text(value, 'category', 60, True).strip()
        if name in categories:
            return name
        if name in aliases:
            return aliases[name]
        raise ValueError('Unbekannte Kategorie: ' + name)
    cat = category(ai.get('category', aliases['Unkategorisiert']))
    payment = text(ai.get('payment_method',''), 'payment_method', 60).strip()
    if payment and not con.execute('SELECT 1 FROM payment_methods WHERE name=?', (payment,)).fetchone():
        raise ValueError('Unbekanntes Zahlungsmittel: ' + payment)
    notes = text(ai.get('notes',''), 'notes', max_notes)
    group = text(ai.get('group_name',''), 'group_name', 80).strip()
    parts = ai.get('items', [])
    if not isinstance(parts, list) or len(parts) > 200:
        raise ValueError('items: höchstens 200 Positionen erwartet.')
    converted = []
    for part in parts:
        if not isinstance(part, dict) or set(part) - {'name','amount','category','group_name'}:
            raise ValueError('Ungültige Positionsfelder.')
        own = part.get('group_name')
        if own is not None:
            own = text(own, 'Positionsgruppe', 80).strip()
        converted.append(dict(name=text(part.get('name'),'Positionsname',200,True).strip(),amount=money(part.get('amount')),category=category(part.get('category',cat)),group_name=own))
    # Decimal text avoids binary floating-point conversion of signed integer cents.
    def decimal(value):
        return format(Decimal(value)/100, '.2f')
    for part in converted:
        part['amount'] = decimal(part['amount'])
    return dict(date=day,merchant=title,amount=decimal(amount),kind='expense',category=cat,payment_method=payment,notes=notes,group_name=group,items=converted)


def transaction(entry, day, con):
    kind = entry.get('kind', 'expense')
    if kind not in ('expense','income'):
        raise ValueError('kind muss expense oder income sein.')
    mapped = {key:value for key,value in entry.items() if key not in ('merchant','kind')}
    mapped['title'] = entry['merchant']
    data = legacy_transaction(mapped, day, con, max_notes=4000)
    data['kind'] = kind
    return data


def ingest(body, db):
    day, fields, identity, canonical = envelope(body)
    legacy = isinstance(body, dict) and set(body) == {'timestamp','original_message','ai'}
    with closing(ledger.connect(db)) as con, con:
        con.execute('BEGIN IMMEDIATE')
        previous = con.execute('SELECT transaction_id,payload FROM shortcut_imports WHERE request_id=?', (identity,)).fetchone()
        if previous:
            if previous['payload'] != canonical:
                raise ImportConflict('request_id wurde bereits mit anderen Buchungsdaten verwendet.')
            if previous[0] is None:
                raise DeletedImport('Der ursprüngliche Eintrag wurde gelöscht; derselbe Aufruf wird nicht erneut angelegt.')
            txid, duplicate = previous[0], True
        else:
            prior = con.execute('SELECT id FROM transactions WHERE import_key=?', ('shortcut:'+identity,)).fetchone()
            if prior:
                if not legacy and 'request_id' in body:
                    raise ImportConflict('request_id ist bereits vorhanden, aber die ursprüngliche Quellenhistorie fehlt. Buchung in der App prüfen.')
                txid, duplicate = prior[0], True
            else:
                data = legacy_transaction(fields, day, con) if legacy else transaction(fields, day, con)
                txid = ledger.save_transaction(data, db=db, _connection=con)['id']
                con.execute('UPDATE transactions SET import_key=? WHERE id=?', ('shortcut:'+identity,txid))
                duplicate = False
            con.execute('INSERT INTO shortcut_imports VALUES (?,?,?,?)', (identity,txid,canonical,datetime.datetime.now(datetime.timezone.utc).isoformat()))
    return {'id':identity,'status':'completed','count':1,'entry_ids':[txid],'duplicate':duplicate}, 200 if duplicate else 201
