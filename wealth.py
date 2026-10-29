"""Separate wealth ledger. Money is integer EUR cents; transfers never are expenses."""
import calendar
from contextlib import closing
from copy import deepcopy
import datetime as dt
from decimal import Decimal, ROUND_HALF_UP
import json
import re
from urllib.parse import urlencode
from urllib.request import urlopen

KINDS = ('cash', 'brokerage', 'building', 'fixed', 'savings', 'other')
MAX = 99_999_999_999


def empty():
    return dict(version=1, assets=[], plans=[], events=[])


def integer(value, low=0, high=MAX):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Ungültiger ganzzahliger Vermögenswert.')
    return value


def text(value, limit=100, required=True):
    if not isinstance(value, str) or len(value) > limit or '\0' in value or required and not value.strip():
        raise ValueError('Bezeichnung fehlt oder ist zu lang.')
    return value.strip()


def day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Datum als JJJJ-MM-TT angeben.')
    dt.date.fromisoformat(value)
    return value


def rounded(numerator, denominator):
    return int((Decimal(numerator) / denominator).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def validate(doc):
    if not isinstance(doc, dict) or doc.get('version') != 1:
        raise ValueError('Unbekanntes Vermögensformat.')
    for key, maximum in [('assets', 100), ('plans', 200), ('events', 10000)]:
        if not isinstance(doc.get(key), list) or len(doc[key]) > maximum:
            raise ValueError('Zu viele Vermögenseinträge.')
    ids = set()
    names = set()
    for a in doc['assets']:
        identity = integer(a['id'], 1)
        if identity in ids or a['type'] not in KINDS:
            raise ValueError('Ungültige Anlage-ID oder Produktart.')
        ids.add(identity)
        text(a['name']); integer(a['rate_bp'], -10000, 10000)
        if a['name'].strip().lower() in names:
            raise ValueError('Anlagenamen müssen eindeutig sein.')
        names.add(a['name'].strip().lower())
        if a['maturity']:
            day(a['maturity'])
        elif a['type'] == 'fixed':
            raise ValueError('Für Festgeld ein Laufzeitende angeben.')
        if not 1 <= len(a['snapshots']) <= 1000 or len(a['positions']) > 100:
            raise ValueError('Ungültige Bestandswerte.')
        dates = set()
        for s in a['snapshots']:
            day(s['date']); integer(s['value']); integer(s['seq'])
            if s['date'] in dates:
                raise ValueError('Bestandsdatum doppelt.')
            dates.add(s['date'])
        symbols = set()
        for p in a['positions']:
            text(p['name']); text(p['symbol'], 30, False)
            if p['symbol'] and not re.fullmatch(r'[A-Za-z0-9.^_-]{1,30}', p['symbol']):
                raise ValueError('Ungültiges Börsensymbol.')
            integer(p['units'], 0, 10**12); integer(p['price'], 0, 10**12)
            day(p['date'])
            if p['name'] in symbols or a['type'] != 'brokerage':
                raise ValueError('Positionen nur im Depot; Positionsnamen müssen eindeutig sein.')
            symbols.add(p['name'])
    plan_ids = set()
    for p in doc['plans']:
        integer(p['from'], 1); integer(p['to'], 1)
        identity = integer(p['id'], 1)
        if identity in plan_ids or p['from'] not in ids or p['to'] not in ids or p['from'] == p['to']:
            raise ValueError('Ungültiger Dauerauftrag.')
        plan_ids.add(identity); text(p['name']); integer(p['amount'], 1)
        integer(p['every'], 1, 12); day(p['start'])
        if p['end'] and day(p['end']) < p['start']:
            raise ValueError('Ende liegt vor dem Beginn.')
        if type(p['enabled']) is not bool:
            raise ValueError('Ungültiger Dauerauftragsstatus.')
    event_ids, occurrences, linked = set(), set(), set()
    for e in doc['events']:
        integer(e['from']); integer(e['to'], 1)
        identity = integer(e['id'], 1)
        if identity in event_ids:
            raise ValueError('Doppelte Vermögensbuchung.')
        event_ids.add(identity); day(e['date']); integer(e['amount'], 1)
        text(e['note'], 500, False)
        if e['kind'] not in ('transfer', 'interest', 'dividend', 'fee', 'buy', 'sell'):
            raise ValueError('Ungültige Vermögensbuchungsart.')
        if e['to'] not in ids or e['kind'] == 'transfer' and (e['from'] not in ids or e['from'] == e['to']):
            raise ValueError('Ungültige Vermögensreferenz.')
        if e['kind'] != 'transfer' and e['from'] != 0:
            raise ValueError('Ungültige Gegenbuchung.')
        integer(e['plan'], 0)
        if e['plan']:
            occurrence = (e['plan'], e['date'])
            if e['plan'] not in plan_ids or occurrence in occurrences:
                raise ValueError('Doppelter oder unbekannter Dauerauftragstermin.')
            occurrences.add(occurrence)
        if not isinstance(e['entries'], list) or len(e['entries']) > 2:
            raise ValueError('Höchstens zwei Bankbuchungen verknüpfen.')
        for identity in e['entries']:
            integer(identity, 1)
            if identity in linked or e['kind'] != 'transfer':
                raise ValueError('Bankbuchung bereits zugeordnet.')
            linked.add(identity)
    maximum_event = max(event_ids, default=0)
    if any(s['seq'] > maximum_event for a in doc['assets'] for s in a['snapshots']):
        raise ValueError('Bestandswert verweist auf eine unbekannte Buchungsfolge.')
    for a in doc['assets']:
        integer(holding(a))
        integer(cash(doc, a, dt.date.today().isoformat()))
        integer(cash(doc, a, dt.date.today().isoformat()) + holding(a))
    return doc


def load(con):
    row = con.execute('SELECT data FROM wealth_state WHERE id=1').fetchone()
    return json.loads(row[0]) if row else empty()


def store(con, doc):
    validate(doc)
    if doc == empty():
        con.execute('DELETE FROM wealth_state')
        return
    con.execute('INSERT INTO wealth_state VALUES (1,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                (json.dumps(doc, ensure_ascii=False, separators=(',', ':')),))


def linked_entries(doc):
    return {i for e in doc['events'] for i in e['entries']}


def asset(doc, identity):
    return next((a for a in doc['assets'] if a['id'] == identity), None)


def cash(doc, a, date):
    snapshots = [s for s in a['snapshots'] if s['date'] <= date]
    if not snapshots:
        return 0
    s = max(snapshots, key=lambda s: s['date'])
    value = s['value']
    for e in doc['events']:
        if e['date'] > date or e['date'] < s['date'] or e['date'] == s['date'] and e['id'] <= s['seq']:
            continue
        if e['kind'] == 'transfer':
            value += e['amount'] * ((e['to'] == a['id']) - (e['from'] == a['id']))
        elif e['to'] == a['id']:
            value += e['amount'] * (-1 if e['kind'] in ('fee', 'buy') else 1)
    return value


def holding(a):
    return sum(rounded(p['units'] * p['price'], 10**10) for p in a['positions'])


def next_id(rows):
    return max((x['id'] for x in rows), default=0) + 1


def month_date(start, offset):
    date = dt.date.fromisoformat(start)
    y, m = divmod(date.year * 12 + date.month - 1 + offset, 12)
    return dt.date(y, m + 1, min(date.day, calendar.monthrange(y, m + 1)[1])).isoformat()


def occurrences(plan, after, until):
    for i in range(1200):
        date = month_date(plan['start'], i * plan['every'])
        if date > until or plan['end'] and date > plan['end']:
            break
        if date > after:
            yield date
    else:
        raise ValueError('Dauerauftrag umfasst mehr als 1200 Termine.')


def post(doc, e, today):
    e = dict(id=next_id(doc['events']), date=day(e['date']), kind=e['kind'],
             amount=integer(e['amount'], 1), **{'from': e.get('from', 0)},
             to=e['to'], note=e.get('note', ''), plan=e.get('plan', 0), entries=e.get('entries', []))
    if e['date'] > today:
        raise ValueError('Zukünftige Buchungen als Dauerauftrag planen.')
    a = asset(doc, e['from'] if e['kind'] == 'transfer' else e['to'])
    if not a or not any(s['date'] <= e['date'] for s in a['snapshots']):
        raise ValueError('Zum Buchungsdatum fehlt ein Anfangsbestand.')
    if e['kind'] in ('transfer', 'fee', 'buy') and cash(doc, a, e['date']) < e['amount']:
        raise ValueError('Das Quellguthaben reicht nicht aus. Bestand prüfen.')
    target = asset(doc, e['to'])
    if not target or not any(s['date'] <= e['date'] for s in target['snapshots']):
        raise ValueError('Zum Buchungsdatum fehlt der Zielbestand.')
    if any(s['date'] > e['date'] for item in (a, target) for s in item['snapshots']):
        raise ValueError('Bewegung liegt vor einem neueren Bestandswert. Historische Korrekturen über Bestandswerte erfassen.')
    doc['events'].append(e)
    validate(doc)
    # Backdated transfers must not overdraw later balances either.
    for a in doc['assets']:
        for date in {today, *(x['date'] for x in doc['events'] if x['date'] >= e['date'])}:
            if cash(doc, a, date) < 0:
                raise ValueError('Die Buchung würde ein späteres Guthaben überziehen.')


def apply(doc, command, today=None):
    today = today or dt.date.today().isoformat()
    op = command['op']
    if op == 'asset':
        old = asset(doc, command.get('id', 0))
        if command.get('id') and old is None:
            raise ValueError('Anlage wurde nicht gefunden.')
        a = deepcopy(old) if old else dict(id=next_id(doc['assets']), snapshots=[], positions=[])
        a.update(name=text(command['name']), type=command['type'], rate_bp=integer(command['rate_bp'], -10000, 10000), maturity=command.get('maturity', ''))
        if 'value' in command:
            date = day(command['date'])
            if date > today:
                raise ValueError('Bestandswerte dürfen nicht in der Zukunft liegen.')
            a['snapshots'] = [s for s in a['snapshots'] if s['date'] != date]
            a['snapshots'].append(dict(date=date, value=integer(command['value']), seq=max((e['id'] for e in doc['events']), default=0)))
        if old:
            doc['assets'][doc['assets'].index(old)] = a
        else:
            doc['assets'].append(a)
    elif op == 'delete-asset':
        identity = command['id']
        if any(identity in (e['from'], e['to']) for e in doc['events'] + doc['plans']):
            raise ValueError('Anlagen mit Buchungen oder Daueraufträgen bleiben für die Historie erhalten.')
        doc['assets'] = [a for a in doc['assets'] if a['id'] != identity]
    elif op == 'plan':
        old = next((p for p in doc['plans'] if p['id'] == command.get('id')), None)
        p = {k: command[k] for k in ('name', 'from', 'to', 'amount', 'every', 'start', 'end', 'enabled')}
        p['id'] = old['id'] if old else next_id(doc['plans'])
        if old and any(e['plan'] == old['id'] for e in doc['events']) and any(p[k] != old[k] for k in ('start', 'every', 'from', 'to')):
            raise ValueError('Gebuchten Dauerauftrag pausieren und einen neuen anlegen, um Termine oder Konten zu ändern.')
        if old:
            doc['plans'][doc['plans'].index(old)] = p
        else:
            doc['plans'].append(p)
    elif op == 'event':
        post(doc, command, today)
    elif op == 'link':
        e = next((e for e in doc['events'] if e['id'] == command['id'] and e['kind'] == 'transfer'), None)
        if not e:
            raise ValueError('Vermögensumbuchung wurde nicht gefunden.')
        e['entries'] = command['entries']
    elif op == 'delete-position':
        a = asset(doc, command['id'])
        if not a:
            raise ValueError('Depot fehlt.')
        p = next((p for p in a['positions'] if p['name'] == command['name']), None)
        if not p or p['units']:
            raise ValueError('Vor dem Entfernen Bestand auf null setzen oder Position verkaufen.')
        a['positions'].remove(p)
    elif op == 'run-plans':
        booked = {(e['plan'], e['date']) for e in doc['events']}
        due = sorted((date, p['id'], p) for p in doc['plans'] if p['enabled'] for date in occurrences(p, '0001-01-01', today) if (p['id'], date) not in booked)
        for date, _, p in due:
            post(doc, dict(date=date, kind='transfer', amount=p['amount'], to=p['to'], note=p['name'], plan=p['id'], **{'from': p['from']}), today)
    elif op in ('position', 'trade'):
        a = asset(doc, command['id'])
        if not a or a['type'] != 'brokerage':
            raise ValueError('Ein Depot auswählen.')
        name = text(command['name'])
        old = next((p for p in a['positions'] if p['name'] == name), None)
        p = dict(name=name, symbol=command.get('symbol', ''), units=integer(command['units'], 0, 10**12), price=integer(command['price'], 0, 10**12), date=day(command['date']))
        if p['date'] > today:
            raise ValueError('Kursdatum liegt in der Zukunft.')
        if op == 'trade':
            if p['date'] != today:
                raise ValueError('Wertpapierhandel zunächst nur mit heutigem Datum erfassen; historische Bestände über Bestandskorrektur setzen.')
            if p['units'] <= 0 or p['price'] <= 0:
                raise ValueError('Stückzahl und Kurs müssen positiv sein.')
            sell = command.get('sell', False)
            if sell and (not old or old['units'] < p['units']):
                raise ValueError('Nicht genügend Wertpapieranteile.')
            post(doc, dict(date=p['date'], kind='sell' if sell else 'buy', amount=rounded(p['units'] * p['price'], 10**10), to=a['id'], note=('Verkauf ' if sell else 'Kauf ') + name), today)
            p['units'] = (old['units'] if old else 0) + (-p['units'] if sell else p['units'])
        if old:
            a['positions'][a['positions'].index(old)] = p
        else:
            a['positions'].append(p)
    else:
        raise ValueError('Unbekannte Vermögensaktion.')
    validate(doc)
    return doc


def forecast(doc, months=120, delta=0, today=None):
    today = today or dt.date.today().isoformat()
    integer(months, 1, 360)
    balances = {a['id']: cash(doc, a, today) for a in doc['assets']}
    invested = {a['id']: holding(a) for a in doc['assets']}
    accrual = dict.fromkeys(balances, 0)
    last = month_date(today, months)
    due = {}
    for p in doc['plans']:
        if p['enabled']:
            for date in occurrences(p, today, last):
                due.setdefault(date, []).append(p)
    points = [dict(date=today, total=sum(balances.values()) + sum(invested.values()), growth=0)]
    targets = {month_date(today, m) for m in range(1, months + 1)}
    current, growth, skipped = dt.date.fromisoformat(today), 0, 0
    while current.isoformat() < last:
        current += dt.timedelta(days=1)
        date = current.isoformat()
        for a in doc['assets']:
            rate = max(-10000, min(10000, a['rate_bp'] + (delta if a['type'] == 'brokerage' else 0)))
            if not a['maturity'] or date <= a['maturity']:
                basis = invested[a['id']] if a['type'] == 'brokerage' else balances[a['id']]
                accrual[a['id']] += basis * rate
            if current.day == calendar.monthrange(current.year, current.month)[1] or date == a['maturity']:
                interest = rounded(accrual[a['id']], 3650000)
                target = invested if a['type'] == 'brokerage' else balances
                target[a['id']] += interest
                integer(target[a['id']], 0, MAX)
                accrual[a['id']] = 0
                growth += interest
        for p in sorted(due.get(date, []), key=lambda p: p['id']):
            if balances[p['from']] >= p['amount']:
                balances[p['from']] -= p['amount']; balances[p['to']] += p['amount']
                integer(balances[p['to']], 0, MAX)
            else:
                skipped += 1
        if date in targets:
            points.append(dict(date=date, total=sum(balances.values()) + sum(invested.values()), growth=growth))
    return dict(points=points, skipped=skipped)


def report(doc, months=120, today=None):
    today = today or dt.date.today().isoformat()
    values = [dict(id=a['id'], cash=cash(doc, a, today), holdings=holding(a), total=cash(doc, a, today) + holding(a)) for a in doc['assets']]
    return dict(document=doc, values=values, total=sum(a['total'] for a in values),
                scenarios=[dict(name=name, **forecast(doc, months, delta, today)) for name, delta in [('Vorsichtig', -200), ('Annahme', 0), ('Optimistisch', 200)]])


def update(db, command):
    import app as ledger
    with closing(ledger.connect(db)) as con, con:
        con.execute('BEGIN IMMEDIATE')
        doc = load(con)
        apply(doc, command)
        # Link only existing whole expense/reimbursement entries of this dataset.
        for e in doc['events']:
            signs = []
            for identity in e['entries']:
                row = con.execute('SELECT * FROM transactions WHERE id=?', (identity,)).fetchone()
                if not row or row['kind'] != 'expense' or abs(row['amount']) != e['amount'] or row['group_name'] or con.execute('SELECT 1 FROM items WHERE transaction_id=?', (identity,)).fetchone():
                    raise ValueError('Nur passende, ungeteilte Bankbuchungen ohne Gruppe zuordnen.')
                signs.append(row['amount'] > 0)
            if len(signs) == 2 and signs[0] == signs[1]:
                raise ValueError('Zwei zugeordnete Bankbuchungen müssen entgegengesetzte Vorzeichen haben.')
        store(con, doc)
    return dict(ok=True)


def fetch_quote(symbol, key):
    if not re.fullmatch(r'[A-Za-z0-9.^_-]{1,30}', symbol) or not re.fullmatch(r'[A-Za-z0-9]{1,100}', key):
        raise ValueError('Börsensymbol oder API-Schlüssel ungültig.')
    url = 'https://www.alphavantage.co/query?' + urlencode(dict(function='GLOBAL_QUOTE', symbol=symbol, apikey=key))
    try:
        with urlopen(url, timeout=10) as response:
            raw = response.read(100001)
        if len(raw) > 100000:
            raise ValueError('Kursantwort zu groß.')
        quote = json.loads(raw)['Global Quote']
        if quote['01. symbol'].upper() != symbol.upper():
            raise ValueError('Kurs gehört zu einem anderen Symbol.')
        price = Decimal(quote['05. price'])
        if not price.is_finite() or not 0 < price <= 1000000:
            raise ValueError('Ungültiger Kurs.')
        date = day(quote['07. latest trading day'])
        if date > dt.date.today().isoformat():
            raise ValueError('Kursdatum liegt in der Zukunft.')
        return dict(price=int((price * 1000000).quantize(Decimal(1), rounding=ROUND_HALF_UP)), date=date)
    except Exception:
        raise ValueError('Kein Kurs verfügbar. Symbol, kostenloses API-Limit und Verbindung prüfen. Bisheriger Kurs bleibt erhalten.') from None


def quote_update(db, command):
    import app as ledger
    # One selected position per user action. No background requests or retries.
    with closing(ledger.connect(db)) as con:
        doc = load(con)
    a = asset(doc, command['id'])
    p = next((p for p in a['positions'] if p['name'] == command['name']), None) if a else None
    if not p or not command.get('eur_confirmed'):
        raise ValueError('Vor dem Abruf bestätigen, dass das Börsensymbol in EUR notiert.')
    result = fetch_quote(p['symbol'], command['key'])
    with closing(ledger.connect(db)) as con, con:
        con.execute('BEGIN IMMEDIATE')
        latest = load(con)
        current_asset = asset(latest, command['id'])
        current = next((x for x in current_asset['positions'] if x['name'] == p['name']), None) if current_asset else None
        if current != p:
            raise ValueError('Position wurde inzwischen geändert. Bitte erneut öffnen.')
        if result['date'] < current['date']:
            raise ValueError('Anbieter liefert einen älteren Kurs; gespeicherter Kurs bleibt erhalten.')
        current.update(result)
        store(con, latest)
    return dict(ok=True)
