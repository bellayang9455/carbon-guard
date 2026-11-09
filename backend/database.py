"""SQLite / PostgreSQL 資料庫入口。設定 DATABASE_URL 時不會回退到本機資料庫。"""
import sqlite3
from contextlib import contextmanager
from urllib.parse import urlsplit, parse_qs
from .config import DB, DATABASE_URL

WRITE_LOCK = 741930126
TABLE_COLUMNS = {
    'users': ['username','password','role','supplier'],
    'sessions': ['token_hash','username','csrf','expires'],
    'records': ['id','payload','previous_hash','digest','mac'],
    'audit': ['id','payload','previous_hash','digest','mac'],
    'semiconductor_records': ['id','payload','previous_hash','digest','mac'],
    'models': ['id','payload','mac','saved_order'],
    'semiconductor_models': ['id','payload','mac','saved_order'],
}

class Row(dict):
    def __getitem__(self, key):
        return tuple(self.values())[key] if isinstance(key, int) else super().__getitem__(key)

class Cursor:
    def __init__(self, cursor): self.cursor=cursor
    def fetchone(self):
        row=self.cursor.fetchone()
        return Row(row) if row is not None else None
    def fetchall(self): return [Row(row) for row in self.cursor.fetchall()]
    def __iter__(self):
        for row in self.cursor: yield Row(row)

class PostgresConnection:
    def __init__(self, connection): self.connection=connection
    def execute(self, sql, values=()):
        if sql.strip().upper() == 'BEGIN IMMEDIATE':
            # 所有鏈的追加寫入使用相同交易鎖，避免兩個請求產生相同編號／分叉。
            return Cursor(self.connection.execute('SELECT pg_advisory_xact_lock(%s)',(WRITE_LOCK,)))
        # 本專案的查詢皆為固定 SQL，? 僅用於參數佔位，不接受任意使用者 SQL。
        return Cursor(self.connection.execute(sql.replace('?', '%s'), values))
    def commit(self): self.connection.commit()
    def rollback(self): self.connection.rollback()
    def close(self): self.connection.close()

@contextmanager
def connect():
    if DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row
        options=dict(connect_timeout=20, row_factory=dict_row, prepare_threshold=None)
        parsed=urlsplit(DATABASE_URL)
        if parsed.hostname not in ('localhost','127.0.0.1','::1'):
            sslmode=parse_qs(parsed.query).get('sslmode',['require'])[0]
            if sslmode not in ('require','verify-ca','verify-full'):
                raise RuntimeError('外部 PostgreSQL 連線需要啟用 SSL')
            options['sslmode']=sslmode
        db=PostgresConnection(psycopg.connect(DATABASE_URL, **options))
    else:
        db=sqlite3.connect(DB, timeout=30)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def initialize():
    statements=[
        "CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY,password TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('admin','supplier')),supplier TEXT NOT NULL)",
        'CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,username TEXT NOT NULL REFERENCES users(username),csrf TEXT NOT NULL,expires DOUBLE PRECISION NOT NULL)',
        *[f'CREATE TABLE IF NOT EXISTS {table}(id INTEGER PRIMARY KEY,payload TEXT NOT NULL,previous_hash TEXT NOT NULL,digest TEXT NOT NULL,mac TEXT NOT NULL)' for table in ('records','audit','semiconductor_records')],
        *[f'CREATE TABLE IF NOT EXISTS {table}(id TEXT PRIMARY KEY,payload TEXT NOT NULL,mac TEXT NOT NULL,saved_order BIGINT NOT NULL DEFAULT 0)' for table in ('models','semiconductor_models')],
    ]
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for statement in statements: db.execute(statement)
        if not DATABASE_URL:
            # 舊 SQLite 原檔就地增加排序欄位，不改動既有 payload / HMAC。
            for table in ('models','semiconductor_models'):
                names={r['name'] for r in db.execute(f'PRAGMA table_info({table})')}
                if 'saved_order' not in names:
                    db.execute(f'ALTER TABLE {table} ADD COLUMN saved_order BIGINT NOT NULL DEFAULT 0')
                db.execute(f'UPDATE {table} SET saved_order=rowid WHERE saved_order=0')

def bootstrap_admin():
    """讓沒有雲端 Shell 的免費服務，能透過環境設定建立第一個管理員。"""
    import os
    name=os.getenv('BOOTSTRAP_ADMIN_USERNAME','').strip()
    password=os.getenv('BOOTSTRAP_ADMIN_PASSWORD','')
    if not name and not password:return
    if not 1<=len(name)<=80 or not 12<=len(password)<=256:
        raise RuntimeError('初始化管理員需要帳號與12–256字元密碼')
    from .security import password_hash
    from .integrity import ensure_valid,append
    from datetime import datetime,timezone
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT username FROM users WHERE role='admin'").fetchone():return
        if db.execute('SELECT username FROM users WHERE username=?',(name,)).fetchone():
            raise RuntimeError('初始化帳號已存在但不是管理員')
        ensure_valid(db)
        db.execute('INSERT INTO users VALUES (?,?,?,?)',(name,password_hash(password),'admin',''))
        append(db,'audit',{'time':datetime.now(timezone.utc).isoformat(),'user':name,'action':'admin_created','detail':{}})
