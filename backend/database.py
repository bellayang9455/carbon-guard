import sqlite3
from contextlib import contextmanager
from .config import DB

@contextmanager
def connect():
    db = sqlite3.connect(DB, timeout=30)
    db.row_factory = sqlite3.Row
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
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users(
            username TEXT PRIMARY KEY, password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','supplier')),
            supplier TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(
            token_hash TEXT PRIMARY KEY, username TEXT NOT NULL REFERENCES users(username),
            csrf TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS records(
            id INTEGER PRIMARY KEY, payload TEXT NOT NULL,
            previous_hash TEXT NOT NULL, digest TEXT NOT NULL, mac TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(
            id INTEGER PRIMARY KEY, payload TEXT NOT NULL,
            previous_hash TEXT NOT NULL, digest TEXT NOT NULL, mac TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS semiconductor_records(
            id INTEGER PRIMARY KEY, payload TEXT NOT NULL,
            previous_hash TEXT NOT NULL, digest TEXT NOT NULL, mac TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS models(
            id TEXT PRIMARY KEY, payload TEXT NOT NULL, mac TEXT NOT NULL);
        ''')
