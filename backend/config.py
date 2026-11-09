import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv('CARBON_DATA_DIR', str(ROOT / 'data')))
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'carbon.sqlite3'
SECRET = os.getenv('CARBON_SECRET', '')
if len(SECRET) < 32:
    raise RuntimeError('CARBON_SECRET 必須設定為至少 32 字元的隨機密鑰')
SECURE_COOKIE = os.getenv('CARBON_SECURE_COOKIE', 'false').lower() == 'true'
