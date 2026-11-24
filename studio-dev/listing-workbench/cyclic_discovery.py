"""Offline, account-isolated discovery observations. Never selection evidence."""
import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit
from app_paths import DATA
from amazon_selection_capture import MARKETS

DB = DATA / 'cyclic_discovery.sqlite3'
TRUST = 'unverified_observation'


def _text(value, name, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError('Invalid ' + name)
    return value.strip()


def _id(value, name='id'):
    value = _text(value, name, 100)
    if not re.fullmatch(r'[A-Za-z0-9_.:-]+', value):
        raise ValueError('Invalid ' + name)
    return value


def _owner(user):
    if type(user) is not int or user <= 0:
        raise ValueError('Invalid owner')
    return user


def _norm(value):
    return ' '.join(re.findall(r'[^\W_]+', unicodedata.normalize('NFKC', value).casefold()))


def _asin(value):
    value = _text(value, 'asin', 10).upper()
    if not re.fullmatch('[A-Z0-9]{10}', value):
        raise ValueError('Invalid ASIN')
    return value


def _url(value, market, route, target):
    value = _text(value, 'url', 4000)
    p = urlsplit(value)
    try:
        port = p.port
    except ValueError as exc:
        raise ValueError('Invalid URL port') from exc
    host = (p.hostname or '').lower().removeprefix('www.')
    if p.scheme != 'https' or p.username is not None or p.password is not None or port not in (None, 443) or MARKETS.get(host) != market:
        raise ValueError('URL must be credential-free official Amazon HTTPS for the same market')
    pairs = parse_qsl(p.query, keep_blank_values=True)
    q = {}
    for key, val in pairs:
        if key in ('k', 'me', 'seller'):
            if key in q:
                raise ValueError('Duplicate identifying URL parameter')
            q[key] = val
    if route == 'product':
        m = re.search(r'/dp/([A-Za-z0-9]{10})(?:/|$)', p.path)
        if not m or m.group(1).upper() != target or q:
            raise ValueError('Product URL ASIN mismatch')
        path, query = '/dp/' + target, ''
    else:
        key = {'search': 'k', 'store': 'me', 'seller': 'seller'}[route]
        paths = ('/sp', '/gp/help/seller/at-a-glance.html') if route == 'seller' else ('/s',)
        observed_path = p.path
        if route == 'seller' and observed_path == '/gp/help/seller/at-a-glance.html/ref=dp_merchant_link':
            observed_path = '/gp/help/seller/at-a-glance.html'
        if observed_path not in paths or q != {key: target}:
            raise ValueError('URL context mismatch')
        path, query = observed_path, urlencode({key: target})
    return urlunsplit(('https', host, path, query, ''))


def _products(value, search=False):
    if not isinstance(value, list) or not 1 <= len(value) <= 50:
        raise ValueError('Expected 1-50 visible products')
    found = {}
    for row in value:
        if not isinstance(row, dict):
            raise ValueError('Invalid product')
        item = {'asin': _asin(row.get('asin')), 'title': _text(row.get('title'), 'title')}
        if row.get('brand'):
            item['brand'] = _text(row['brand'], 'brand', 300)
        if search and row.get('similarity') is not None:
            if row['similarity'] not in ('EXACT', 'CLOSE', 'RELATED', 'REJECT'):
                raise ValueError('Invalid similarity')
            item['similarity'] = row['similarity']
            item['similarityTrust'] = 'reported_unverified'
        if search and row.get('matchNotes'):
            item['matchNotes'] = _text(row['matchNotes'], 'matchNotes')
        if item['asin'] in found and found[item['asin']] != item:
            raise ValueError('Conflicting duplicate ASIN')
        found[item['asin']] = item
    return list(found.values())


def _clean(raw):
    if not isinstance(raw, dict):
        raise ValueError('Invalid event')
    kind = raw.get('kind')
    market = raw.get('marketplace')
    if kind not in ('keyword', 'search', 'seller', 'store') or market not in MARKETS.values() or raw.get('sourceType') != 'browser_visible':
        raise ValueError('Invalid event kind, market or sourceType')
    e = {'id': _id(raw.get('id')), 'kind': kind, 'marketplace': market,
         'parentId': None if raw.get('parentId') in (None, '') else _id(raw['parentId']),
         'sourceType': 'browser_visible'}
    try:
        dt = datetime.fromisoformat(_text(raw.get('observedAt'), 'observedAt', 80).replace('Z', '+00:00'))
    except (ValueError, TypeError) as exc:
        raise ValueError('Invalid observation time') from exc
    if dt.tzinfo is None or dt > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError('Observation time must have timezone and not be in the future')
    e['observedAt'] = dt.astimezone(timezone.utc).isoformat()
    if kind == 'keyword':
        e.update(asin=_asin(raw.get('asin')), sourceTitle=_text(raw.get('sourceTitle'), 'sourceTitle'), phrase=_text(raw.get('phrase'), 'phrase', 300))
        if raw.get('brand'):
            e['brand'] = _text(raw['brand'], 'brand', 300)
        phrase, title = _norm(e['phrase']), _norm(e['sourceTitle'])
        starts = [title]
        brand = _norm(e.get('brand', ''))
        if brand and title.startswith(brand + ' '):
            starts.append(title[len(brand) + 1:])
        if not phrase or not any(t == phrase or t.startswith(phrase + ' ') for t in starts):
            raise ValueError('Keyword must be a title opening phrase')
        e['normalizedPhrase'] = phrase
        e['url'] = _url(raw.get('url'), market, 'product', e['asin'])
    elif kind == 'search':
        e['query'] = _text(raw.get('query'), 'query', 300)
        e['url'] = _url(raw.get('url'), market, 'search', e['query'])
        # An empty visible result list is a valid search observation.
        e['products'] = [] if raw.get('products') == [] else _products(raw.get('products'), True)
    else:
        seller = _text(raw.get('sellerId'), 'sellerId', 30)
        if not re.fullmatch('[A-Z0-9]{5,30}', seller):
            raise ValueError('Invalid sellerId')
        e['sellerId'] = seller
        if kind == 'seller':
            e['asin'] = _asin(raw.get('asin'))
            e['sellerName'] = _text(raw.get('sellerName'), 'sellerName', 500)
            e['sellerLabel'] = _text(raw.get('sellerLabel'), 'sellerLabel', 1000)
            if raw.get('sellerLinkSource') != 'visible_sold_by_link':
                raise ValueError('Seller requires visible Sold by link')
            e['sellerLinkSource'] = 'visible_sold_by_link'
            e['sellerLink'] = _url(raw.get('sellerLink'), market, 'seller', seller)
            e['url'] = _url(raw.get('url'), market, 'product', e['asin'])
        else:
            e['url'] = _url(raw.get('url'), market, 'store', seller)
            e['status'] = raw.get('status')
            if e['status'] == 'captured':
                e['products'] = _products(raw.get('products'))
            elif e['status'] == 'inaccessible' and raw.get('products') == []:
                e['products'] = []
                e['reason'] = _text(raw.get('reason'), 'reason')
            else:
                raise ValueError('Invalid store status/products')
    return e


def _validate_graph(events):
    rounds = {}
    # Iterative traversal permits unordered batches and avoids recursion limits.
    pending = dict(events)
    while pending:
        progressed = False
        for eid, e in list(pending.items()):
            pid = e['parentId']
            if pid is None:
                if e['kind'] != 'keyword':
                    raise ValueError('Only keyword may be a root')
                rounds[eid] = 1
            else:
                if pid not in events:
                    raise ValueError('Missing parent event')
                if pid not in rounds:
                    continue
                p = events[pid]
                expected = {'keyword': 'store', 'search': 'keyword', 'seller': 'search', 'store': 'seller'}[e['kind']]
                if p['kind'] != expected or p['marketplace'] != e['marketplace'] or e['observedAt'] < p['observedAt']:
                    raise ValueError('Wrong predecessor, market or time')
                if e['kind'] == 'keyword':
                    match = next((x for x in p['products'] if x['asin'] == e['asin']), None)
                    if not match or match['title'] != e['sourceTitle'] or match.get('brand', '') != e.get('brand', ''):
                        raise ValueError('Keyword does not belong to captured store product')
                elif e['kind'] == 'search' and e['query'] != p['phrase']:
                    raise ValueError('Search query differs from source phrase')
                elif e['kind'] == 'seller' and e['asin'] not in [x['asin'] for x in p['products']]:
                    raise ValueError('Seller product not present in search')
                elif e['kind'] == 'store' and e['sellerId'] != p['sellerId']:
                    raise ValueError('Store seller mismatch')
                rounds[eid] = rounds[pid] + (e['kind'] == 'keyword')
            del pending[eid]
            progressed = True
        if not progressed:
            raise ValueError('Cyclic event ancestry')
    return rounds


def _connect(write=False):
    if not write and not DB.exists():
        return None
    if write:
        DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB) if write else DB.resolve().as_uri() + '?mode=ro', uri=not write, timeout=10)
    return c


def _schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS discovery_cycles (owner INTEGER NOT NULL, cycle TEXT NOT NULL, revision INTEGER NOT NULL, PRIMARY KEY(owner,cycle))')
    c.execute('CREATE TABLE IF NOT EXISTS discovery_events (owner INTEGER NOT NULL, cycle TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(owner,cycle,id))')


def _load(c, user, cycle):
    if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='discovery_cycles'").fetchone():
        raise ValueError('Discovery cycle not found')
    row = c.execute('SELECT revision FROM discovery_cycles WHERE owner=? AND cycle=?', (user, cycle)).fetchone()
    if row is None:
        raise ValueError('Discovery cycle not found')
    events = {r[0]: json.loads(r[1]) for r in c.execute('SELECT id,payload FROM discovery_events WHERE owner=? AND cycle=? ORDER BY rowid', (user, cycle))}
    return row[0], events


def ingest(user, data):
    _owner(user)
    if not isinstance(data, dict):
        raise ValueError('Invalid batch')
    cycle = _id(data.get('cycleId'), 'cycleId')
    revision = data.get('expectedRevision')
    if type(revision) is not int or revision < 0:
        raise ValueError('expectedRevision must be a nonnegative integer')
    if not isinstance(data.get('events'), list) or not 1 <= len(data['events']) <= 100:
        raise ValueError('Expected 1-100 events per batch')
    incoming = [_clean(e) for e in data['events']]
    c = _connect(True)
    try:
        c.execute('BEGIN IMMEDIATE')
        _schema(c)
        row = c.execute('SELECT revision FROM discovery_cycles WHERE owner=? AND cycle=?', (user, cycle)).fetchone()
        current, events = _load(c, user, cycle) if row else (0, {})
        new = {}
        for e in incoming:
            old = events.get(e['id'], new.get(e['id']))
            if old is not None and old != e:
                raise ValueError('Conflicting event ID; batch rejected')
            if old is None:
                new[e['id']] = e
        if new and revision != current:
            raise ValueError('Stale expectedRevision')
        if len(events) + len(new) > 5000:
            raise ValueError('Cycle limit exceeded')
        events.update(new)
        _validate_graph(events)
        if new:
            current += 1
            c.execute('INSERT OR REPLACE INTO discovery_cycles VALUES (?,?,?)', (user, cycle, current))
            c.executemany('INSERT INTO discovery_events VALUES (?,?,?,?)', [(user, cycle, eid, json.dumps(e, ensure_ascii=False, sort_keys=True)) for eid, e in new.items()])
        result = _report(cycle, current, events)
        c.commit()
        return result
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def report(user, cycle_id):
    _owner(user)
    cycle_id = _id(cycle_id, 'cycleId')
    c = _connect()
    if c is None:
        raise ValueError('Discovery cycle not found')
    try:
        c.execute('BEGIN')
        revision, events = _load(c, user, cycle_id)
        return _report(cycle_id, revision, events)
    finally:
        c.close()


def prepare_keyword(user, data):
    """Prepare a title prefix from a recorded seller-list card; never writes."""
    _owner(user)
    if not isinstance(data, dict) or set(data) != {'cycleId', 'expectedRevision', 'parentId', 'asin', 'phrase'}:
        raise ValueError('Expected cycleId, expectedRevision, parentId, asin and phrase only')
    cycle = _id(data.get('cycleId'), 'cycleId')
    parent_id = _id(data.get('parentId'), 'parentId')
    asin = _asin(data.get('asin'))
    phrase = _text(data.get('phrase'), 'phrase', 300)
    revision = data.get('expectedRevision')
    if type(revision) is not int or revision < 0:
        raise ValueError('Invalid expectedRevision')
    current = report(user, cycle)
    if current['revision'] != revision:
        raise ValueError('Stale expectedRevision')
    parent = next((e for e in current['events'] if e['id'] == parent_id), None)
    if not parent or parent['kind'] != 'store' or parent['status'] != 'captured':
        raise ValueError('Captured seller listing parent required')
    product = next((p for p in parent['products'] if p['asin'] == asin), None)
    if not product:
        raise ValueError('Product not present in captured seller listing')
    host = next(h for h, market in MARKETS.items() if market == parent['marketplace'])
    # Observation time belongs to the original listing, not a new browser read.
    event = _clean({'id': 'prepared', 'kind': 'keyword', 'parentId': parent_id,
                    'marketplace': parent['marketplace'], 'sourceType': 'browser_visible',
                    'observedAt': parent['observedAt'], 'asin': asin,
                    'sourceTitle': product['title'], 'phrase': phrase,
                    **({'brand': product['brand']} if product.get('brand') else {}),
                    'url': 'https://' + host + '/dp/' + asin})
    event['id'] = 'keyword-' + hashlib.sha256(json.dumps(
        {'cycleId': cycle, 'event': event}, sort_keys=True, ensure_ascii=True).encode()).hexdigest()[:40]
    # Reuse all ancestry/market/time checks; the following save rechecks revision.
    existing = {e['id']: _clean(e) for e in current['events']}
    old = existing.get(event['id'])
    if old is not None and old != event:
        raise ValueError('Conflicting prepared keyword')
    existing[event['id']] = event
    _validate_graph(existing)
    return {'status': 'prepared', 'readOnly': True, 'trust': TRUST,
            'qualificationEvaluated': False, 'executionAllowed': False,
            'sourceKind': 'seller_listing_card', 'sourceObservationTime': parent['observedAt'],
            'derivedFrom': {'eventId': parent_id, 'sellerId': parent['sellerId'],
                            'asin': asin, 'listedTitle': product['title']},
            'preparedBatch': {'cycleId': cycle, 'expectedRevision': revision, 'events': [event]},
            'limitations': 'Derived from the recorded listing-card title. No new product-page read, search, qualification or product import occurred.'}


def history(user):
    _owner(user)
    c = _connect()
    if c is None:
        return {'items': []}
    try:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='discovery_cycles'").fetchone():
            return {'items': []}
        return {'items': [{'cycleId': r[0], 'revision': r[1], 'eventCount': r[2]} for r in c.execute('SELECT c.cycle,c.revision,COUNT(e.id) FROM discovery_cycles c LEFT JOIN discovery_events e ON e.owner=c.owner AND e.cycle=c.cycle WHERE c.owner=? GROUP BY c.cycle,c.revision ORDER BY c.rowid DESC', (user,))]}
    finally:
        c.close()


def _report(cycle, revision, events):
    rounds = _validate_graph(events)
    keywords, products, sellers, stores, edges, queue = {}, {}, {}, {}, [], []
    def provenance(e):
        return {'eventId': e['id'], 'parentId': e['parentId'], 'sourceURL': e['url'], 'observedAt': e['observedAt'], 'trust': TRUST, 'round': rounds[e['id']]}
    def product(e, item):
        key = e['marketplace'] + ':' + item['asin']
        node = products.setdefault(key, {'id': key, 'asin': item['asin'], 'marketplace': e['marketplace'], 'sources': []})
        node['sources'].append({**item, **provenance(e)})
        return key
    def edge(e, relation, a, b):
        edges.append({'relation': relation, 'fromId': a, 'toId': b, **provenance(e)})
    for e in events.values():
        market, kind = e['marketplace'], e['kind']
        if kind == 'keyword':
            key = market + ':' + e['normalizedPhrase']
            node = keywords.setdefault(key, {'id': key, 'normalizedPhrase': e['normalizedPhrase'], 'marketplace': market, 'sources': []})
            node['sources'].append({**e, **provenance(e)})
            pk = product(e, {'asin': e['asin'], 'title': e['sourceTitle'], **({'brand': e['brand']} if 'brand' in e else {})})
            edge(e, 'title_generated_keyword', pk, key)
        elif kind == 'search':
            parent = events[e['parentId']]
            for item in e['products']:
                edge(e, 'searched_to_product', market + ':' + parent['normalizedPhrase'], product(e, item))
        elif kind == 'seller':
            key = market + ':' + e['sellerId']
            node = sellers.setdefault(key, {'id': key, 'sellerId': e['sellerId'], 'marketplace': market, 'sources': []})
            node['sources'].append({**e, **provenance(e)})
            edge(e, 'sold_by_observed', market + ':' + e['asin'], key)
        else:
            sk = market + ':' + e['sellerId']
            key = 'store:' + sk
            node = stores.setdefault(key, {'id': key, 'sellerId': e['sellerId'], 'marketplace': market, 'sources': []})
            node['sources'].append({**e, **provenance(e)})
            edge(e, 'seller_store_observed', sk, key)
            for item in e['products']:
                edge(e, 'store_listed_product', key, product(e, item))
    searched = {(e['marketplace'], events[e['parentId']]['normalizedPhrase']) for e in events.values() if e['kind'] == 'search'}
    for e in events.values():
        kids = [x for x in events.values() if x['parentId'] == e['id']]
        def enqueue(status, asin=None):
            queue.append({'eventId': e['id'], 'sourceASIN': asin, 'status': status, 'executionAllowed': False})
        if e['kind'] == 'keyword' and not kids:
            enqueue('duplicate_keyword_already_searched' if (e['marketplace'], e['normalizedPhrase']) in searched else 'pending_search_capture', e['asin'])
        elif e['kind'] == 'search':
            if not e['products']:
                enqueue('no_new_products')
            for item in e['products']:
                if not any(k['asin'] == item['asin'] for k in kids):
                    enqueue('needs_review' if item.get('similarity') == 'REJECT' else 'needs_seller_capture', item['asin'])
        elif e['kind'] == 'seller' and not kids:
            enqueue('needs_store_capture', e['asin'])
        elif e['kind'] == 'store':
            if e['status'] == 'inaccessible':
                enqueue('needs_review')
            for item in e['products']:
                if not any(k['asin'] == item['asin'] for k in kids):
                    enqueue('needs_title_phrase_capture', item['asin'])
    return {'cycleId': cycle, 'revision': revision, 'eventCount': len(events), 'roundCount': max(rounds.values(), default=0),
            'events': [{**e, **provenance(e)} for e in events.values()],
            'keywords': list(keywords.values()), 'products': list(products.values()), 'sellers': list(sellers.values()), 'stores': list(stores.values()), 'edges': edges, 'queue': queue,
            'nextActions': queue, 'blockers': ['Observations have not been independently verified; execution and qualification are disabled.'],
            'counts': {'discoveredProducts': len(products), 'recordedSellers': len(sellers), 'qualified': 0, 'imported': 0, 'keywords': len(keywords), 'products': len(products), 'sellers': len(sellers), 'stores': len(stores), 'edges': len(edges)},
            'qualificationEvaluated': False, 'qualifiedCount': 0, 'importedCount': 0, 'executionAllowed': False, 'externalCallsPerformed': 0, 'externalCallsScope': 'ledger_ingestion_only',
            'limitations': 'This ledger records supplied observations and performs no browser or external calls itself. Browser authenticity and product qualification are not independently established. No ranking, sourcing, profit evaluation or product import was performed by this ledger.'}


def template(market='US'):
    if market not in MARKETS.values():
        raise ValueError('Invalid marketplace')
    common = {'id': '', 'parentId': None, 'kind': '', 'marketplace': market, 'observedAt': '', 'sourceType': 'browser_visible', 'url': ''}
    return {'formatVersion': 1, 'cycleId': '', 'expectedRevision': 0, 'events': [],
            'eventTemplates': {
                'keyword': {**common, 'kind': 'keyword', 'asin': '', 'sourceTitle': '', 'brand': '', 'phrase': ''},
                'search': {**common, 'kind': 'search', 'query': '', 'products': []},
                'seller': {**common, 'kind': 'seller', 'asin': '', 'sellerId': '', 'sellerName': '', 'sellerLabel': '', 'sellerLink': '', 'sellerLinkSource': 'visible_sold_by_link'},
                'store': {**common, 'kind': 'store', 'sellerId': '', 'status': 'captured', 'products': [], 'reason': ''}},
            'productTemplate': {'asin': '', 'title': '', 'brand': ''},
            'instructions': ['Blank format reference, not captured evidence.', 'Use timezone-aware observedAt and official same-market Amazon URLs.', 'Parent chain: keyword -> search -> seller -> store -> keyword.', 'Search products may additionally report similarity EXACT/CLOSE/RELATED/REJECT and matchNotes; never verified.', 'Store captured requires 1-50 products; inaccessible requires empty products and reason.', 'Unknown fields are discarded. No automated execution or qualification.']}
