import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv('CARBON_DATA_DIR', str(ROOT / 'data')))
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
if DATABASE_URL and not DATABASE_URL.startswith(('postgresql://','postgres://')):
    raise RuntimeError('DATABASE_URL 必須是 PostgreSQL 連線網址')
if not DATABASE_URL:
    DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'carbon.sqlite3'
SECRET = os.getenv('CARBON_SECRET', '')
if len(SECRET) < 32:
    raise RuntimeError('CARBON_SECRET 必須設定為至少 32 字元的隨機密鑰')
SECURE_COOKIE = os.getenv('CARBON_SECURE_COOKIE', 'false').lower() == 'true'
