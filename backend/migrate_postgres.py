"""將唯讀 SQLite 快照搬到空的 PostgreSQL；不覆寫既有目標資料。"""
import argparse
import hashlib
import hmac
import sqlite3
from pathlib import Path
from .config import DATABASE_URL
from .database import initialize,connect,TABLE_COLUMNS
from .integrity import verify,signature

def migrate(source_path):
    if not DATABASE_URL:raise RuntimeError('請先設定 DATABASE_URL；目標必須是 PostgreSQL')
    source_path=Path(source_path).resolve()
    if not source_path.is_file():raise RuntimeError('來源 SQLite 檔案不存在')
    source=sqlite3.connect(source_path.as_uri()+'?mode=ro',uri=True)
    source.row_factory=sqlite3.Row
    try:
        source.execute('BEGIN')
        existing={r['name'] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'users','records','audit'}.issubset(existing):raise RuntimeError('來源不是支援的 CarbonGuard SQLite')
        for table in ('records','audit','semiconductor_records'):
            if table in existing and not verify(source,table)['valid']:
                raise RuntimeError('來源完整性驗證失敗；請確認 CARBON_SECRET 與原系統一致')
        for table,prefix in [('models','model:'),('semiconductor_models','semiconductor-model:')]:
            if table in existing:
                for row in source.execute(f'SELECT payload,mac FROM {table}'):
                    if not hmac.compare_digest(row['mac'],signature(prefix+row['payload'])):
                        raise RuntimeError('來源模型驗證失敗；請確認原密鑰')
        initialize()
        counts={}
        with connect() as target:
            target.execute('BEGIN IMMEDIATE')
            for table in TABLE_COLUMNS:
                if target.execute(f'SELECT COUNT(*) AS n FROM {table}').fetchone()['n']:
                    raise RuntimeError('目標資料庫不是空的，已取消；不會覆寫既有資料')
            for table,columns in TABLE_COLUMNS.items():
                if table=='sessions' or table not in existing:continue
                order='rowid' if table in ('models','semiconductor_models') else ('username' if table=='users' else 'id')
                for row in source.execute(f'SELECT rowid AS __legacy_order,* FROM {table} ORDER BY {order}'):
                    values=dict(row)
                    if table in ('models','semiconductor_models'):
                        values['saved_order']=values.get('saved_order') or values['__legacy_order']
                    target.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",tuple(values[column] for column in columns))
                    counts[table]=counts.get(table,0)+1
            for table in ('records','audit','semiconductor_records'):
                if not verify(target,table)['valid']:raise RuntimeError('目標驗證失敗，交易已取消')
        return counts
    finally:
        source.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True,help='原 carbon.sqlite3 路徑')
    args=parser.parse_args()
    try:
        counts=migrate(args.source)
    except Exception as exc:
        # 不輸出連線字串、資料內容或資料庫例外細節。
        if isinstance(exc,RuntimeError):print(str(exc))
        else:print('搬移失敗；請確認連線、來源檔案與表格格式，目標交易已取消。')
        raise SystemExit(1)
    print('搬移完成：',counts)
    print('未搬移登入 Session，請使用原帳密重新登入。原 SQLite 未修改。')
