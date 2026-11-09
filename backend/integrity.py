import hashlib
import hmac
import json
from .config import SECRET

TABLES = {'records', 'audit', 'semiconductor_records'}

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)

def signature(value):
    return hmac.new(SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()

def fingerprint(table, number, payload, previous):
    return hashlib.sha256(canonical({
        'table': table, 'id': number, 'payload': payload,
        'previous_hash': previous,
    }).encode()).hexdigest()

def verify(db, table):
    if table not in TABLES:
        raise ValueError('Invalid table')
    previous, invalid, count = 'GENESIS', [], 0
    for row in db.execute(f'SELECT * FROM {table} ORDER BY id'):
        count += 1
        expected = fingerprint(table, row['id'], row['payload'], previous)
        if (row['id'] != count or row['previous_hash'] != previous
                or row['digest'] != expected
                or not hmac.compare_digest(row['mac'], signature(table + ':' + expected))):
            invalid.append(row['id'])
        previous = row['digest']
    return {'valid': not invalid, 'count': count, 'head': previous, 'invalid_ids': invalid}

def append(db, table, value):
    if table not in TABLES:
        raise ValueError('Invalid table')
    last = db.execute(f'SELECT id,digest FROM {table} ORDER BY id DESC LIMIT 1').fetchone()
    number, previous = (last['id'] + 1, last['digest']) if last else (1, 'GENESIS')
    payload = canonical(value)
    digest = fingerprint(table, number, payload, previous)
    db.execute(f'INSERT INTO {table} VALUES (?,?,?,?,?)',
               (number, payload, previous, digest, signature(table + ':' + digest)))
    return {'id': number, **value, 'hash': digest}

def ensure_valid(db):
    for table in TABLES:
        if not verify(db, table)['valid']:
            raise ValueError('資料完整性失敗，已停止寫入')
