"""Own-account configuration and conservative internal transfer matching."""
from contextlib import nullcontext
import datetime
from collections import Counter
import re
from decimal import Decimal, InvalidOperation

import app as ledger


def normalize_iban(value):
    if not isinstance(value, str):
        raise ValueError('Ungültige IBAN.')
    iban = re.sub(r'\s+', '', value).upper()
    if not iban:
        return ''
    if not re.fullmatch(r'[A-Z]{2}\d{2}[A-Z0-9]{11,30}', iban):
        raise ValueError('Ungültige IBAN.')
    number = ''.join(str(ord(c)-55) if c.isalpha() else c for c in iban[4:]+iban[:4])
    if int(number) % 97 != 1:
        raise ValueError('IBAN-Prüfsumme stimmt nicht.')
    return iban


def configure_account(data, db, *, _connection=None, _reconcile=True):
    name = data.get('name')
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 60:
        raise ValueError('Kontoname muss 1–60 Zeichen enthalten.')
    try:
        share = Decimal(str(data.get('share_percent', '100')))
        if not share.is_finite() or not 0 <= share <= 100 or share * 100 != (share * 100).to_integral_value():
            raise ValueError('Anteil muss zwischen 0 und 100 Prozent liegen (höchstens zwei Nachkommastellen).')
    except InvalidOperation:
        raise ValueError('Ungültiger Anteil.') from None
    share_income = data.get('share_income', True)
    if not isinstance(share_income, bool):
        raise ValueError('Ungültige Anteilseinstellung.')
    iban = normalize_iban(data.get('iban', ''))
    with (nullcontext(_connection) if _connection is not None else ledger.connect(db)) as con:
        if iban and con.execute('SELECT 1 FROM account_settings WHERE iban=? AND payment_method!=?', (iban, name.strip())).fetchone():
            raise ValueError('Diese IBAN ist bereits einem Konto zugeordnet.')
        con.execute('INSERT OR IGNORE INTO payment_methods VALUES (?)', (name.strip(),))
        con.execute('DELETE FROM payment_types WHERE name=?', (name.strip(),))
        con.execute('INSERT INTO account_settings VALUES (?,?,?,?) ON CONFLICT(payment_method) DO UPDATE SET share_bp=excluded.share_bp,share_income=excluded.share_income,iban=excluded.iban',
                    (name.strip(), int(share * 100), int(share_income), iban))
    if _reconcile: reconcile_transfers(db)
    return {'ok': True}


def payment_details(db):
    with ledger.connect(db) as con:
        bank = {row['payment_method']: dict(row) for row in con.execute('SELECT * FROM account_settings')}
        types = dict(con.execute('SELECT name,kind FROM payment_types'))
        return [dict(name=row[0], kind='bank' if row[0] in bank else types.get(row[0], 'cash' if row[0]=='Bar' else 'other')) for row in con.execute('SELECT name FROM payment_methods ORDER BY name')]


def configure_payment(data, db):
    name = data.get('name')
    if not isinstance(name, str) or not name.strip() or len(name.strip())>60:
        raise ValueError('Name muss 1–60 Zeichen enthalten.')
    name = name.strip()
    kind = data.get('kind')
    if kind not in ('bank','cash','other'): raise ValueError('Unbekannter Zahlungsmitteltyp.')
    with ledger.connect(db) as con:
        con.execute('BEGIN IMMEDIATE')
        if kind == 'bank':
            configure_account(data, db, _connection=con, _reconcile=False)
        else:
            con.execute('INSERT OR IGNORE INTO payment_methods VALUES (?)', (name,))
            for table in ('transfer_links','transfer_ignored'):
                con.execute(f'DELETE FROM {table} WHERE outgoing_id IN (SELECT id FROM transactions WHERE payment_method=?) OR incoming_id IN (SELECT id FROM transactions WHERE payment_method=?)', (name,name))
            con.execute('DELETE FROM account_settings WHERE payment_method=?', (name,))
            con.execute('INSERT INTO payment_types VALUES (?,?) ON CONFLICT(name) DO UPDATE SET kind=excluded.kind', (name,kind))
    reconcile_transfers(db)
    return {'ok': True}


def candidate_pairs(con):
    settings = {row['payment_method']: dict(row) for row in con.execute('SELECT * FROM account_settings')}
    rows = [dict(row) for row in con.execute("SELECT * FROM transactions WHERE amount!=0 AND group_name='' AND NOT EXISTS(SELECT 1 FROM items WHERE transaction_id=transactions.id AND group_name IS NOT NULL AND group_name!='')") if row['payment_method'] in settings]
    pairs = []
    ignored = {tuple(row) for row in con.execute('SELECT outgoing_id,incoming_id FROM transfer_ignored')}
    incoming_by_key = {}
    for incoming in rows:
        if incoming['amount'] < 0:
            incoming_by_key.setdefault((-incoming['amount'],incoming['date']), []).append(incoming)
    for outgoing in rows:
        if outgoing['amount'] <= 0:
            continue
        nearby = []
        day = datetime.date.fromisoformat(outgoing['date'])
        for delta in range(-3,4):
            nearby.extend(incoming_by_key.get((outgoing['amount'],(day+datetime.timedelta(days=delta)).isoformat()), []))
        for incoming in nearby:
            if incoming['amount'] != -outgoing['amount'] or incoming['payment_method'] == outgoing['payment_method']:
                continue
            if abs((datetime.date.fromisoformat(outgoing['date'])-datetime.date.fromisoformat(incoming['date'])).days) > 3:
                continue
            if (outgoing['id'],incoming['id']) in ignored:
                continue
            out_bank,in_bank = settings[outgoing['payment_method']],settings[incoming['payment_method']]
            def mentions(tx, iban):
                return bool(iban) and (tx['counterparty_iban'] == iban or iban in re.sub(r'\s+', '', tx['merchant']).upper())
            keyword = r'umbuchung|kontoübertrag|kontouebertrag|übertrag|uebertrag|eigenüberweisung|eigenueberweisung'
            evidence = mentions(outgoing,in_bank['iban']) or mentions(incoming,out_bank['iban']) or (re.search(keyword,outgoing['merchant'],re.I) and re.search(keyword,incoming['merchant'],re.I))
            pairs.append({'outgoing_id':outgoing['id'],'incoming_id':incoming['id'],'evidence':bool(evidence)})
    return pairs


def reconcile_transfers(db):
    with ledger.connect(db) as con:
        con.execute('DELETE FROM transfer_links WHERE manual=0')
        # Remove stale manual links after amount/account edits, and never match a leg twice.
        for link in list(con.execute('SELECT * FROM transfer_links')):
            rows=list(con.execute('SELECT * FROM transactions WHERE id IN (?,?)',(link['outgoing_id'],link['incoming_id'])))
            by_id={row['id']:row for row in rows}
            grouped_items=con.execute("SELECT 1 FROM items WHERE transaction_id IN (?,?) AND group_name IS NOT NULL AND group_name!='' LIMIT 1",(link['outgoing_id'],link['incoming_id'])).fetchone()
            if len(rows)!=2 or by_id[link['outgoing_id']]['amount']<=0 or by_id[link['incoming_id']]['amount']>=0 or sum(row['amount'] for row in rows)!=0 or rows[0]['payment_method']==rows[1]['payment_method'] or any(row['group_name'] for row in rows) or grouped_items:
                con.execute('DELETE FROM transfer_links WHERE outgoing_id=?',(link['outgoing_id'],))
        used={row[0] for row in con.execute('SELECT outgoing_id FROM transfer_links UNION SELECT incoming_id FROM transfer_links')}
        pairs=[p for p in candidate_pairs(con) if p['outgoing_id'] not in used and p['incoming_id'] not in used]
        out_counts=Counter(p['outgoing_id'] for p in pairs);in_counts=Counter(p['incoming_id'] for p in pairs)
        for pair in pairs:
            if pair['evidence'] and out_counts[pair['outgoing_id']]==1 and in_counts[pair['incoming_id']]==1:
                con.execute('INSERT INTO transfer_links VALUES (?,?,0)',(pair['outgoing_id'],pair['incoming_id']))


def confirm_transfer(data, db):
    outgoing,incoming=int(data['outgoing_id']),int(data['incoming_id'])
    with ledger.connect(db) as con:
        if not any(p['outgoing_id']==outgoing and p['incoming_id']==incoming for p in candidate_pairs(con)):
            raise ValueError('Keine passenden Gegenbuchungen auf unterschiedlichen eigenen Konten.')
        used={row[0] for row in con.execute('SELECT outgoing_id FROM transfer_links UNION SELECT incoming_id FROM transfer_links')}
        if outgoing in used or incoming in used:
            raise ValueError('Eine Buchung ist bereits zugeordnet.')
        con.execute('INSERT INTO transfer_links VALUES (?,?,1)',(outgoing,incoming))
    return {'ok': True}

def reject_transfer(data, db):
    outgoing,incoming=int(data['outgoing_id']),int(data['incoming_id'])
    with ledger.connect(db) as con:
        con.execute('DELETE FROM transfer_links WHERE outgoing_id=? AND incoming_id=?',(outgoing,incoming))
        if con.execute('SELECT count(*) FROM transactions WHERE id IN (?,?)',(outgoing,incoming)).fetchone()[0]!=2:
            raise ValueError('Buchungen nicht gefunden.')
        con.execute('INSERT OR IGNORE INTO transfer_ignored VALUES (?,?)',(outgoing,incoming))
    return {'ok':True}
