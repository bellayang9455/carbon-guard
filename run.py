"""自動載入 .env；可跨平台執行管理指令或啟動伺服器。"""
import os
import sys
import runpy
from pathlib import Path
root = Path(__file__).resolve().parent
os.chdir(root)
if (root / '.env').exists():
    for line in (root / '.env').read_text(encoding='utf-8').splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip())
if len(sys.argv) > 1:
    sys.argv = ['backend.manage', *sys.argv[1:]]
    runpy.run_module('backend.manage', run_name='__main__')
else:
    import uvicorn
    uvicorn.run('backend.main:app', host=os.getenv('CARBON_HOST', '127.0.0.1'),
                port=int(os.getenv('PORT', '8000')), workers=1)
