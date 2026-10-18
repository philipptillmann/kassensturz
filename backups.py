"""Portable financial-dataset ZIPs; never restore credentials or execute archive SQL."""
from contextlib import closing, contextmanager
import datetime
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import zipfile

import app as ledger
import accounts
import shortcut_api
from tools.export_android import write_archive

MAX_ARCHIVE_BYTES = 544_000_000
MAX_METADATA = 16_000_000
MAX_RECEIPT = 4_000_000
MAX_RECEIPTS = 512_000_000
TABLES = ('shortcut_imports', 'transfer_ignored', 'transfer_links', 'receipt_images', 'items',
          'transactions', 'account_settings', 'category_aliases', 'payment_methods', 'categories')


def text(value, limit, empty=True):
    if not isinstance(value, str) or len(value) > limit or '\x00' in value or (not empty and not value.strip()):
        raise ValueError('Ungültiger Text in der Sicherung.')
    return value


def integer(value, low=-(2**63)+1, high=2**63-1):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Ungültiger ganzzahliger Wert in der Sicherung.')
    return value


def flag(value):
    if type(value) is not bool:
        raise ValueError('Ungültiger Wahrheitswert in der Sicherung.')
    return value


def names(value):
    if not isinstance(value, list) or len(value) > 2000:
        raise ValueError('Zu viele Kategorien oder Zahlungsmittel.')
    result = [text(name, 60, False) for name in value]
    if len(set(result)) != len(result):
        raise ValueError('Doppelte Kategorien oder Zahlungsmittel.')
    return result


def bounded_read(stream, maximum):
    data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError('Archivinhalt ist zu groß.')
    return data


def _insert_metadata(meta, con):
    if not isinstance(meta, dict) or meta.get('format') != 'kassensturz-android' or type(meta.get('version')) is not int or meta['version'] != 1:
        raise ValueError('Unbekanntes Kassensturz-Sicherungsformat.')
    cats, payments = names(meta['categories']), names(meta['payments'])
    if not cats:
        raise ValueError('Kategorien fehlen.')
    aliases = meta.get('server_aliases', {})
    if not isinstance(aliases, dict) or len(aliases) > 2000:
        raise ValueError('Ungültige Kategoriezuordnungen.')
    aliases = {text(k, 60, False): text(v, 60, False) for k, v in aliases.items()}
    if any(value not in cats for value in aliases.values()):
        raise ValueError('Kategoriezuordnung verweist auf unbekannte Kategorie.')
    # Native backups have no alias history. Preserve their names and add only
    # defaults needed by server-side OCR/import suggestions.
    for default in ledger.CATEGORIES:
        if default not in aliases:
            if default not in cats:
                cats.append(default)
            aliases[default] = default
    if len(cats) > 2000:
        raise ValueError('Zu viele Kategorien nach Ergänzung der Standardzuordnungen.')
    con.executemany('INSERT INTO categories VALUES (?)', [(c,) for c in cats])
    con.executemany('INSERT INTO category_aliases VALUES (?,?)', aliases.items())
    con.executemany('INSERT INTO payment_methods VALUES (?)', [(p,) for p in payments])
    rows = meta['entries']
    if not isinstance(rows, list) or len(rows) > 50000:
        raise ValueError('Zu viele Buchungen.')
    receipts, entries = set(), {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Ungültige Buchung.')
        txid = integer(row['id'], 1)
        if txid in entries:
            raise ValueError('Doppelte Buchungs-ID.')
        day = text(row['date'], 10, False)
        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', day):
            raise ValueError('Ungültiges Buchungsdatum.')
        datetime.date.fromisoformat(day)
        merchant = text(row['merchant'], 4000, False)
        amount = integer(row['amount'])
        category = text(row['category'], 60, False)
        payment = text(row['payment'], 60)
        if category not in cats or payment and payment not in payments:
            raise ValueError('Unbekannte Kategorie oder Zahlungsmittel.')
        kind = row['kind']
        if kind not in ('expense', 'income') or kind == 'income' and amount > 0:
            raise ValueError('Ungültige Buchungsart oder Einnahme.')
        notes, group = text(row['notes'], 10000), text(row['group'], 100)
        counterparty = text(row['counterparty'], 34)
        key = row.get('import_key')
        if key is not None:
            text(key, 512, False)
        con.execute('INSERT INTO transactions(id,date,merchant,amount,category,import_key,group_name,payment_method,kind,notes,counterparty_iban) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                    (txid,day,merchant,amount,category,key,group,payment,kind,notes,counterparty))
        parts = row['parts']
        if not isinstance(parts, list) or len(parts) > 2000:
            raise ValueError('Zu viele Positionen.')
        part_sum, grouped = 0, bool(group)
        for part in parts:
            name, value = text(part['name'], 4000, False), integer(part['amount'])
            cat = text(part['category'], 60, False)
            own_group = part.get('group')
            if own_group is not None:
                text(own_group, 100)
            if cat not in cats:
                raise ValueError('Unbekannte Positionskategorie.')
            part_sum += value
            grouped = grouped or bool(own_group)
            part_id = integer(part['id'], 1) if 'id' in part else None
            con.execute('INSERT INTO items(id,transaction_id,name,amount,category,group_name) VALUES (?,?,?,?,?,?)', (part_id,txid,name,value,cat,own_group))
        if parts and part_sum != amount:
            raise ValueError('Positionssumme stimmt nicht mit Buchung überein.')
        if flag(row['receipt']):
            receipts.add(txid)
        entries[txid] = (amount,payment,grouped)
    settings = meta['accounts']
    if not isinstance(settings, list) or len(settings) > 2000:
        raise ValueError('Zu viele Konten.')
    for setting in settings:
        name = text(setting['name'], 60, False)
        share = integer(setting['share'], 0, 10000)
        iban = accounts.normalize_iban(text(setting['iban'], 42))
        if name not in payments:
            raise ValueError('Kontozahlungsmittel fehlt.')
        if iban and con.execute('SELECT 1 FROM account_settings WHERE iban=?', (iban,)).fetchone():
            raise ValueError('Doppelte Konto-IBAN.')
        con.execute('INSERT INTO account_settings VALUES (?,?,?,?)', (name,share,int(flag(setting['share_income'])),iban))
    used = set()
    for field, table in [('transfers','transfer_links'), ('ignored','transfer_ignored')]:
        pairs = meta.get(field, [])
        if not isinstance(pairs, list) or len(pairs) > 50000:
            raise ValueError('Zu viele Umbuchungen.')
        for pair in pairs:
            out, inc = integer(pair['outgoing'], 1), integer(pair['incoming'], 1)
            if out == inc or out not in entries or inc not in entries:
                raise ValueError('Ungültige Umbuchungsreferenz.')
            if field == 'transfers':
                a, b = entries[out], entries[inc]
                if out in used or inc in used or a[0] <= 0 or a[0] != -b[0] or a[1] == b[1] or a[2] or b[2]:
                    raise ValueError('Ungültige bestätigte Umbuchung.')
                used.update((out, inc))
                con.execute('INSERT INTO transfer_links VALUES (?,?,?)', (out,inc,integer(pair.get('manual',1),0,1)))
            else:
                con.execute('INSERT INTO transfer_ignored VALUES (?,?)', (out,inc))
    imports = meta.get('server_shortcut_imports', [])
    if not isinstance(imports, list) or len(imports) > 50000:
        raise ValueError('Zu viele Kurzbefehlsquellen.')
    for source in imports:
        identity = text(source['request_id'], 36, False)
        payload = text(source['payload'], shortcut_api.MAX_BODY)
        _, _, expected_id, _ = shortcut_api.envelope(json.loads(payload))
        txid = source['transaction_id']
        if identity != expected_id or txid is not None and integer(txid, 1) not in entries:
            raise ValueError('Ungültige Kurzbefehlsquelle.')
        con.execute('INSERT INTO shortcut_imports VALUES (?,?,?,?)', (identity,txid,payload,text(source['created_at'],100,False)))
    return receipts, {'entries': len(rows), 'receipts': len(receipts), 'categories': len(cats),
                      'dataset': text(meta.get('dataset','unknown'), 20),
                      'created_at': text(meta.get('created_at',''), 100)}


@contextmanager
def staged_archive(stream, temp_dir=None):
    """Validate into an isolated database. Nothing touches the live dataset yet."""
    try:
        with tempfile.TemporaryDirectory(prefix='kassensturz-restore-', dir=temp_dir) as folder:
            stage = Path(folder) / 'staged.sqlite3'
            ledger.init(stage)
            with closing(ledger.connect(stage)) as con, con:
                for table in TABLES:
                    con.execute('DELETE FROM ' + table)
                with zipfile.ZipFile(stream) as archive:
                    infos = archive.infolist()
                    if not infos or infos[0].filename != 'data.json' or len(infos) > 50001:
                        raise ValueError('Keine gültige Kassensturz-Sicherung.')
                    if infos[0].file_size > MAX_METADATA:
                        raise ValueError('Sicherungsmetadaten sind zu groß.')
                    with archive.open(infos[0]) as file:
                        meta = json.loads(bounded_read(file, MAX_METADATA).decode('utf-8'))
                    expected, summary = _insert_metadata(meta, con)
                    total = 0
                    for info in infos[1:]:
                        if not re.fullmatch(r'receipts/[1-9][0-9]*\.jpg', info.filename) or info.file_size > MAX_RECEIPT:
                            raise ValueError('Unbekannter oder zu großer Archivinhalt.')
                        txid = int(info.filename[9:-4])
                        if txid not in expected:
                            raise ValueError('Doppelter oder unbekannter Beleg.')
                        expected.remove(txid)
                        with archive.open(info) as file:
                            image = bounded_read(file, MAX_RECEIPT)
                        total += len(image)
                        if total > MAX_RECEIPTS or len(image) <= 2 or not image.startswith(b'\xff\xd8'):
                            raise ValueError('Ungültiges oder zu großes Belegarchiv.')
                        con.execute('INSERT INTO receipt_images VALUES (?,?)', (txid,image))
                    if expected:
                        raise ValueError('Belege fehlen in der Sicherung.')
                if con.execute('PRAGMA foreign_key_check').fetchone():
                    raise ValueError('Ungültige Datenreferenzen.')
            yield stage, summary
    except (zipfile.BadZipFile, UnicodeError, json.JSONDecodeError, KeyError, TypeError, sqlite3.IntegrityError, OverflowError, RuntimeError, EOFError) as error:
        raise ValueError('Sicherung ist beschädigt oder enthält ungültige Daten.') from error


def preview(stream, temp_dir=None):
    with staged_archive(stream, temp_dir) as (_, summary):
        return summary


def restore(stream, db):
    with staged_archive(stream, Path(db).parent) as (stage, summary):
        with closing(ledger.connect(db)) as con:
            con.execute('ATTACH DATABASE ? AS restored', (str(stage),))
            with con:
                con.execute('BEGIN IMMEDIATE')
                for table in TABLES:
                    con.execute('DELETE FROM main.' + table)
                for table in reversed(TABLES):
                    cols = ','.join(row[1] for row in con.execute('PRAGMA main.table_info(' + table + ')'))
                    con.execute(f'INSERT INTO main.{table}({cols}) SELECT {cols} FROM restored.{table}')
            con.execute('DETACH DATABASE restored')
        return summary
