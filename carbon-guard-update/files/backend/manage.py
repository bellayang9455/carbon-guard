"""管理指令：python -m backend.manage add-user / checkpoint。"""
import argparse
import getpass
import json
from .database import initialize, connect
from .security import password_hash
from .integrity import verify

parser = argparse.ArgumentParser()
commands = parser.add_subparsers(dest='command', required=True)
add = commands.add_parser('add-user')
add.add_argument('username')
add.add_argument('--role', choices=['admin', 'supplier'], required=True)
add.add_argument('--supplier', default='')
commands.add_parser('checkpoint')
args = parser.parse_args()
initialize()
if args.command == 'add-user':
    if not 1 <= len(args.username) <= 80 or args.username != args.username.strip():
        parser.error('帳號限 1–80 字元，首尾不可空白')
    if args.role == 'supplier' and (not args.supplier.strip() or len(args.supplier.strip()) > 100):
        parser.error('供應商帳號必須指定 --supplier，限 1–100 字元')
    password = getpass.getpass('Password (至少 12 字元): ')
    if len(password) < 12 or len(password) > 256:
        parser.error('密碼長度需為 12–256 字元')
    if password != getpass.getpass('Confirm password: '):
        parser.error('密碼不一致')
    with connect() as db:
        if db.execute('SELECT 1 FROM users WHERE username=?', (args.username,)).fetchone():
            parser.error('帳號已存在')
        db.execute('INSERT INTO users VALUES (?,?,?,?)',
                   (args.username, password_hash(password), args.role, args.supplier.strip()))
    print('帳號已建立')
else:
    with connect() as db:
        result = {table: verify(db, table) for table in ('records', 'audit', 'semiconductor_records')}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not all(value['valid'] for value in result.values()):
        raise SystemExit(1)
