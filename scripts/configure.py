"""只在 .env 不存在時建立本機隨機密鑰。"""
import secrets
from pathlib import Path
root = Path(__file__).resolve().parent.parent
with (root / '.env').open('x', encoding='utf-8') as stream:
    stream.write('CARBON_SECRET=' + secrets.token_hex(32) + '\n')
    stream.write('CARBON_DATA_DIR=./data\nCARBON_SECURE_COOKIE=false\n')
print('已建立 .env，請勿提交或分享此檔案。')
