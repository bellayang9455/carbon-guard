import hashlib
import hmac
import secrets
import time
from fastapi import Cookie, Header, HTTPException, Request
from .database import connect
from .config import SECURE_COOKIE

SESSION_SECONDS = 8 * 3600

def password_hash(password):
    salt = secrets.token_bytes(16)
    value = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 600000)
    return salt.hex() + ':' + value.hex()

def check_password(password, stored):
    salt, expected = stored.split(':')
    value = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000)
    return hmac.compare_digest(value.hex(), expected)

def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()

def current_user(request: Request, carbon_session: str | None = Cookie(default=None),
                 x_csrf_token: str | None = Header(default=None)):
    if not carbon_session:
        raise HTTPException(401, '請先登入')
    with connect() as db:
        row = db.execute('''SELECT u.username,u.role,u.supplier,s.csrf,s.expires
             FROM sessions s JOIN users u ON u.username=s.username
             WHERE s.token_hash=?''', (token_hash(carbon_session),)).fetchone()
    if not row or row['expires'] <= time.time():
        raise HTTPException(401, '登入已過期')
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if not x_csrf_token or not hmac.compare_digest(x_csrf_token, row['csrf']):
            raise HTTPException(403, 'CSRF 驗證失敗')
    return dict(row)

def admin(user):
    if user['role'] != 'admin':
        raise HTTPException(403, '需要管理員權限')
