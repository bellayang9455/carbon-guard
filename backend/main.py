import hashlib
import io
import csv
import json
import secrets
import time
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from . import anomaly, semiconductor
from .config import ROOT, SECURE_COOKIE
from .database import connect, initialize, bootstrap_admin
from .integrity import append, verify, ensure_valid, canonical, signature
from .schemas import Login, Record, Batch, Train, Review
from .security import current_user, admin, check_password, token_hash, SESSION_SECONDS

training_lock = threading.Lock()
login_lock = threading.Lock()
attempts = {}

@asynccontextmanager
async def lifespan(app):
    initialize()
    bootstrap_admin()
    anomaly.restore()
    semiconductor.initialize()
    yield

app = FastAPI(title='CarbonGuard 供應鏈碳排放安全系統', lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)

def now():
    return datetime.now(timezone.utc).isoformat()

def audit(db, user, action, detail):
    return append(db, 'audit', {'time': now(), 'user': user, 'action': action, 'detail': detail})

@app.middleware('http')
async def protection(request: Request, call_next):
    # 對所有請求累計實際讀取大小，不只信任 Content-Length。
    size, parts = 0, []
    async for part in request.stream():
        size += len(part)
        if size > 2 * 1024 * 1024:
            return JSONResponse({'detail': '請求不可超過 2 MB'}, status_code=413)
        parts.append(part)
    request._body = b''.join(parts)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'")
    if request.url.path.startswith('/api'):
        response.headers['Cache-Control'] = 'no-store'
    if SECURE_COOKIE:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    return response

@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse({'detail': '資料完整性驗證失敗，已停止本次操作'}, status_code=409)

@app.get('/api/health')
def health():
    return {'status': 'ok'}

@app.post('/api/login')
def login(body: Login, request: Request, response: Response):
    peer = request.client.host if request.client else 'unknown'
    timestamp = time.time()
    with login_lock:
        for key in list(attempts):
            if timestamp - attempts[key][0] > 300:
                del attempts[key]
        if len(attempts) >= 2048 and peer not in attempts:
            raise HTTPException(429, '登入流量過高，請稍後重試')
        first, count = attempts.get(peer, (timestamp, 0))
        if count >= 10:
            raise HTTPException(429, '登入次數過多，請於五分鐘後重試')
        attempts[peer] = (first, count + 1)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        user = db.execute('SELECT * FROM users WHERE username=?', (body.username,)).fetchone()
        # 不存在的帳號仍執行相同成本的密碼運算。
        dummy = '00' * 16 + ':' + '00' * 32
        matched = check_password(body.password, user['password'] if user else dummy)
        if not user or not matched:
            raise HTTPException(401, '帳號或密碼錯誤')
        ensure_valid(db)
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        db.execute('DELETE FROM sessions WHERE expires<=?', (timestamp,))
        db.execute('INSERT INTO sessions VALUES (?,?,?,?)',
                   (token_hash(token), user['username'], csrf, timestamp + SESSION_SECONDS))
        audit(db, user['username'], 'login', {})
    with login_lock:
        attempts.pop(peer, None)
    response.set_cookie('carbon_session', token, httponly=True, secure=SECURE_COOKIE,
                        samesite='strict', max_age=SESSION_SECONDS, path='/')
    return {'username': user['username'], 'role': user['role'],
            'supplier': user['supplier'], 'csrf': csrf}

@app.get('/api/me')
def me(user=Depends(current_user)):
    return {k: user[k] for k in ('username', 'role', 'supplier', 'csrf')}

@app.post('/api/logout')
def logout(request: Request, response: Response, user=Depends(current_user)):
    with connect() as db:
        db.execute('DELETE FROM sessions WHERE token_hash=?',
                   (token_hash(request.cookies.get('carbon_session', '')),))
    response.delete_cookie('carbon_session', path='/')
    return {'ok': True}

def visible_records(db, user):
    latest = {}
    for event_row in db.execute('SELECT payload FROM audit ORDER BY id DESC'):
        event_value = json.loads(event_row['payload'])
        if event_value.get('action') == 'review':
            number = event_value['detail']['record_id']
            if number not in latest:
                latest[number] = {'decision': event_value['detail']['decision'], 'note': event_value['detail']['note'], 'reviewed_by': event_value['user'], 'reviewed_at': event_value['time']}
    rows = []
    for row in db.execute('SELECT id,payload,digest FROM records ORDER BY id DESC'):
        value = json.loads(row['payload'])
        if user['role'] == 'admin' or value['supplier'] == user['supplier']:
            rows.append({'id': row['id'], **value, 'hash': row['digest'], 'review': latest.get(row['id'])})
    return rows

@app.get('/api/records')
def records(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
            user=Depends(current_user)):
    with connect() as db:
        values = visible_records(db, user)
    return {'total': len(values), 'records': values[offset:offset + limit]}

@app.post('/api/records', status_code=201)
def create(body: Batch, user=Depends(current_user)):
    samples = [row.model_dump() for row in body.records]
    if user['role'] != 'admin' and any(row['supplier'] != user['supplier'] for row in samples):
        raise HTTPException(403, '只能上傳所屬供應商資料')
    # 整批固定使用同一模型版本。
    with anomaly.lock:
        values = [{**row, **anomaly.predict(row), 'created_at': now(),
                   'uploaded_by': user['username']} for row in samples]
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        ensure_valid(db)
        result = [append(db, 'records', row) for row in values]
        audit(db, user['username'], 'upload', {'record_ids': [row['id'] for row in result]})
    return {'records': result}

@app.get('/api/export')
def export(user=Depends(current_user)):
    with connect() as db:
        values = visible_records(db, user)
    columns = ['id', 'supplier', 'month', 'scope', 'emission', 'production',
               'score', 'anomaly', 'model_id', 'created_at', 'hash']
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(columns)
    for row in values:
        cells = []
        for field in columns:
            value = str(row.get(field, '') if row.get(field) is not None else '')
            # 防止試算表公式注入，包括前置空白控制字元。
            if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
                value = "'" + value
            cells.append(value)
        writer.writerow(cells)
    return Response('\ufeff' + stream.getvalue(), media_type='text/csv',
                    headers={'Content-Disposition': 'attachment; filename="carbon-records.csv"'})

@app.get('/api/model')
def model_status(user=Depends(current_user)):
    info = anomaly.status()
    if user['role'] != 'admin':
        return {key: info.get(key) for key in ('trained', 'id', 'created_at')}
    return info

@app.post('/api/model/train')
def train(body: Train, user=Depends(current_user)):
    admin(user)
    if not training_lock.acquire(blocking=False):
        raise HTTPException(409, '已有模型訓練工作執行中')
    try:
        candidate, document = anomaly.prepare(body, user['username'])
        payload = canonical(document)
        with anomaly.lock:
            with connect() as db:
                db.execute('BEGIN IMMEDIATE')
                ensure_valid(db)
                db.execute('INSERT INTO models(id,payload,mac,saved_order) VALUES (?,?,?,?)',
                           (document['id'], payload, signature('model:' + payload), time.time_ns()))
                audit(db, user['username'], 'train', {
                    'model_id': document['id'], 'samples': len(body.samples), 'note': body.note})
            anomaly.activate(candidate, document)
        return anomaly.status()
    finally:
        training_lock.release()

@app.post('/api/predict')
def predict(body: Record, user=Depends(current_user)):
    if user['role'] != 'admin' and body.supplier != user['supplier']:
        raise HTTPException(403, '只能分析所屬供應商資料')
    result = anomaly.predict(body.model_dump())
    if result['model_id'] is None:
        raise HTTPException(409, '尚未訓練模型')
    return result

@app.get('/api/integrity')
def integrity(user=Depends(current_user)):
    admin(user)
    with connect() as db:
        return {table: verify(db, table) for table in ('records', 'audit', 'semiconductor_records')}

@app.get('/api/audit')
def get_audit(user=Depends(current_user)):
    admin(user)
    with connect() as db:
        rows = db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 200').fetchall()
    return [{'id': row['id'], **json.loads(row['payload']), 'hash': row['digest']} for row in rows]

@app.post('/api/records/{number}/review')
def review(number: int, body: Review, user=Depends(current_user)):
    admin(user)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        ensure_valid(db)
        if not db.execute('SELECT id FROM records WHERE id=?', (number,)).fetchone():
            raise HTTPException(404, '紀錄不存在')
        return audit(db, user['username'], 'review', {'record_id': number, **body.model_dump()})

@app.get('/')
def index():
    return FileResponse(ROOT / 'frontend' / 'index.html')

app.mount('/assets', StaticFiles(directory=ROOT / 'frontend'), name='assets')

app.include_router(semiconductor.router)

@app.get('/semiconductor')
def semiconductor_page():
    return FileResponse(ROOT / 'frontend' / 'semiconductor.html')
